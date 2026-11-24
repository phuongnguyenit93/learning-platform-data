# Cân nhắc Scrum khi cần mục tiêu cùng nhịp kiểm tra định kỳ

Một nhóm phát triển nền tảng học trực tuyến nhận nhiều yêu cầu: cải thiện ghi danh khóa học, sửa lỗi quyền truy cập, thiết kế lại trang thanh toán và thử cách hướng dẫn người học vào bài đầu. Nhóm có đủ kỹ năng xây sản phẩm nhưng mỗi người đang theo một danh sách ưu tiên khác nhau. Những cuộc trao đổi với người học diễn ra rời rạc; sau vài tuần, các bên mới phát hiện giao diện đã hoàn tất nhưng API, dữ liệu và kiểm thử chưa tạo được một hành trình có thể sử dụng.

Người quản lý đề xuất: “Hãy chuyển sang Scrum, làm Sprint hai tuần, họp Daily và yêu cầu mỗi Sprint giao 20 story points”. Một thành viên khác đề xuất Kanban vì công việc đến liên tục. Cả hai đề xuất đều có phần hợp lý và phần chưa được kiểm chứng.

Câu hỏi cần trả lời không phải **“Scrum hay Kanban phổ biến hơn?”** mà là:

> **“Dòng công việc này có cần một mục tiêu sản phẩm rõ, một nhóm đủ năng lực tạo Increment, và nhịp cố định để cùng kiểm tra kết quả rồi điều chỉnh kế hoạch hay không?”**

Nếu có, **Scrum đáng để cân nhắc**: nó cung cấp Product Goal, Sprint Goal, những accountabilities rõ, các events tạo nhịp minh bạch–kiểm tra–thích ứng và yêu cầu một Increment có thể sử dụng, đạt Definition of Done. Tuy nhiên, **Scrum không tự giải quyết thiếu quyền ưu tiên, kỹ thuật không kiểm chứng được, phụ thuộc tổ chức hoặc dòng sự cố khẩn liên tục**. Nếu các điều kiện ấy không được xử lý, thêm Sprint và cuộc họp có thể chỉ tạo một lịch báo cáo mới.

Bài học thuộc chương **Lựa chọn cách tiếp cận** của module **AGILE_DEVELOPMENT**. Mục tiêu xuyên suốt module là hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng, giao phần mềm tăng dần, nhận phản hồi sớm, cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo dòng công việc để **chọn cách phối hợp phù hợp với bối cảnh**. Bài này tập trung vào **khi nào nên cân nhắc Scrum vì cần mục tiêu chung và nhịp kiểm tra định kỳ**, không coi Scrum là lựa chọn mặc định cho mọi đội.

> **Thông điệp cốt lõi:** Chọn Scrum để tổ chức **một vòng học về sản phẩm và cách tạo giá trị có trách nhiệm**, không phải để biến mỗi hai tuần thành một kỳ giao chỉ tiêu. Nếu mục tiêu chung, Product Owner, đội đa chức năng và Increment có thể sử dụng đều không tồn tại, cần giải quyết các điều kiện ấy thay vì mong timebox tự tạo ra Agile.

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích sự phù hợp giữa **Product Goal, Sprint Goal, Sprint, Increment** và cơ chế kiểm tra–thích ứng của Scrum.
2. Nhận diện những tín hiệu thực tế cho thấy Scrum hữu ích: **cần tập trung vào một mục tiêu, có cơ hội giao Increment ngắn hạn, cần nhịp đồng bộ stakeholder và quyền thích ứng theo phản hồi**.
3. Phân biệt **Sprint là vòng làm việc tạo giá trị** với lịch báo cáo, batch phát hành bắt buộc hoặc một hợp đồng đóng băng mọi yêu cầu.
4. Nêu đúng accountabilities, events, artifacts và commitments cốt lõi theo **Scrum Guide 2020**, không coi story points, Scrum of Scrums, một công cụ quản lý việc hay TDD là quy định bắt buộc của Scrum.
5. So sánh lựa chọn **Scrum, Kanban và các thực hành kỹ thuật XP**, kể cả trường hợp kết hợp để hỗ trợ flow và chất lượng.
6. Phân tích những tình huống Scrum kém phù hợp hoặc cần bổ sung: sự cố vận hành, backlog khẩn liên tục, thiếu Product Owner thực quyền, nhóm chia theo tầng kỹ thuật, phụ thuộc bên ngoài và chất lượng thấp.
7. Thiết kế thử nghiệm áp dụng Scrum có **Product Goal, Sprint Goal, Definition of Done, dữ liệu flow, outcome và guardrails** để kiểm tra hiệu quả.
8. Thực hành ra quyết định chọn phương pháp trên tình huống nền tảng học trực tuyến, xây một Sprint minh họa và tự phản biện bằng các bài tập có đáp án.

## 1. Bắt đầu từ vấn đề phối hợp, không từ tên framework

Scrum, Kanban hay XP không phải những nhãn thay thế cho chẩn đoán hiện trạng. Một đội có thể gặp nhiều kiểu vấn đề khác nhau và cần cơ chế khác nhau:

| Vấn đề quan sát được | Câu hỏi cần làm rõ | Cơ chế đáng cân nhắc |
|---|---|---|
| Mọi người làm nhiều việc nhưng không rõ mục tiêu chung | Có Product Goal/kết quả người dùng và thứ tự ưu tiên rõ chưa? | Product Goal, Product Backlog và Sprint Goal trong Scrum có thể hữu ích |
| Sau nhiều tuần mới nhận phản hồi sản phẩm | Có thể tạo Increment nhỏ đạt chất lượng và kiểm tra thường xuyên không? | Sprint Review, DoD, tích hợp và phản hồi sớm |
| Công việc khẩn, không dự đoán được, chen vào mỗi ngày | Có thể bảo vệ Sprint Goal hay việc khẩn mới là dịch vụ chính? | Kanban với chính sách kéo việc, WIP/expedite và service review |
| Nhiều việc dở, rất ít việc Done | WIP ở đâu, item nào đang già tuổi? | Kanban flow metrics, WIP control; có thể bổ sung cho Scrum |
| Nhiều lỗi hồi quy và tích hợp cuối kỳ | Đội có CI, test strategy và DoD đủ tin không? | XP practices/TDD/CI/refactoring, DoD và kiểm chứng sớm |
| PO không có quyền ưu tiên, các phòng giao việc mâu thuẫn | Ai tối đa hóa giá trị sản phẩm và có quyền quản lý backlog? | Làm rõ decision rights; đổi nhãn quy trình là chưa đủ |
| Các nhóm UI, API, QA hoàn thành từng phần nhưng không có sản phẩm dùng được | Team boundary và năng lực end-to-end thế nào? | Cross-functional teamwork, vertical slices, hợp đồng và tích hợp |

**Một framework không thể chữa sai vấn đề chỉ vì được triển khai đúng thuật ngữ.** Cần chọn cơ chế nhắm vào nơi dòng giá trị đang bị cản.

### 1.1. Câu hỏi lựa chọn có hai lớp

**Lớp một — cần học và giao giá trị như thế nào?**

- Có một sản phẩm với người dùng và stakeholders đủ rõ không?
- Công việc chủ yếu là **phát triển khả năng sản phẩm mới/cải tiến theo mục tiêu** hay xử lý yêu cầu liên tục theo mức dịch vụ?
- Độ bất định đủ lớn để cần **kiểm tra Increment và cập nhật kế hoạch thường xuyên** không?
- Có thể làm ra **lát cắt có thể sử dụng** trong khoảng thời gian ngắn hợp lý không?

**Lớp hai — điều kiện tổ chức có hỗ trợ Scrum không?**

- Có Product Owner thực quyền với một Product Backlog có thứ tự không?
- Có Scrum Team đủ năng lực cross-functional, self-managing để tạo giá trị không?
- Có thể thống nhất Definition of Done và giữ chất lượng khi thay đổi không?
- Các bên có sẵn sàng kiểm tra phần mềm thực và điều chỉnh thay vì chỉ duyệt kế hoạch không?
- Công việc bất ngờ có thể được quản lý mà không liên tục đe dọa Sprint Goal không?

Nếu câu trả lời ở lớp hai chưa có, **không phải lúc nào cũng bác bỏ Scrum**. Đó có thể là những năng lực và ràng buộc phải cải thiện để Scrum có tác dụng. Nhưng không nên báo rằng đội “đã triển khai Scrum đầy đủ” nếu những điều kiện cốt lõi không được đáp ứng.

### 1.2. Chọn theo cơ chế thay vì giáo điều

Các mục tiêu mà một đội thường muốn:

- **Tập trung:** không nhận vô hạn yêu cầu cùng lúc.
- **Minh bạch:** thấy đúng trạng thái và chất lượng công việc.
- **Phản hồi:** kiểm tra sản phẩm và giả định trước khi chi phí sai tăng.
- **Thích ứng:** đổi kế hoạch theo dữ liệu mới mà không phá mọi cam kết chất lượng.
- **Khả năng dự đoán có điều kiện:** phối hợp được người dùng/stakeholders trong mức bất định.
- **Bền vững:** đội học, cải thiện kỹ thuật và tiếp tục giao giá trị an toàn.

Scrum có thể hỗ trợ những mục tiêu ấy qua cách tổ chức Sprint, nhưng **không phải con đường duy nhất**. Kanban giúp kiểm soát dòng công việc liên tục; XP cung cấp kỷ luật kỹ thuật; chúng có thể bổ sung chứ không tự loại trừ nhau.

## 2. Vì sao “mục tiêu chung” là tín hiệu mạnh để cân nhắc Scrum?

Một nhóm có thể sở hữu một sản phẩm nhưng thực hiện hàng chục hạng mục không liên quan. Khi mọi bên chỉ đo task Done, người dùng khó thấy một bước cải thiện rõ ràng. **Mục tiêu chung** là cơ chế kết nối công việc với một kết quả đáng kiểm chứng.

### 2.1. Product Goal: chúng ta đang đi tới trạng thái sản phẩm nào?

Trong Scrum Guide 2020, **Product Goal** mô tả trạng thái tương lai của sản phẩm, là mục tiêu dài hạn để Scrum Team lập kế hoạch hướng tới; nó là **commitment của Product Backlog**.

Ví dụ nền tảng học:

> **“Học viên đủ điều kiện có thể tự hoàn tất ghi danh khóa được hỗ trợ, nhận đúng quyền và vào bài đầu mà không cần sự can thiệp thủ công trong những trường hợp chuẩn.”**

Mục tiêu này cho phép Product Owner, Developers và stakeholders thảo luận:

- Điều gì đang cản học viên từ ghi danh tới bài đầu?
- Nên ưu tiên xác thực thanh toán hay một banner chiến dịch?
- Có cần chia làm luồng miễn phí trước, hoặc một phương thức thanh toán an toàn trước?
- Dữ liệu nào chứng minh học viên đã hoàn tất hành trình?
- Guardrails về quyền và dữ liệu nào không thể đánh đổi?

Đây không phải một danh sách 30 màn hình/API phải làm đúng thứ tự bất kể phản hồi.

### 2.2. Sprint Goal: trong Sprint này chúng ta muốn đạt điều gì?

**Sprint Goal** là một mục tiêu duy nhất cho Sprint, là commitment của **Sprint Backlog**. Nó giúp Developers tập trung, phối hợp và có không gian lựa chọn cách triển khai khi học thêm.

Ví dụ phù hợp:

> **“Học viên có thể ghi danh một khóa miễn phí hợp lệ và vào bài đầu bằng một luồng đầu-cuối đạt DoD.”**

Ví dụ yếu:

> “Hoàn thành 12 ticket, viết 4 API, sửa 8 bug và đạt 30 story points.”

Câu thứ hai đo danh sách việc, không chỉ ra **giá trị thống nhất**. Nếu team đạt 29/30 story points nhưng học viên không vào được bài, chưa có bằng chứng Sprint Goal đạt.

### 2.3. Product Goal và Sprint Goal không thay thế nhau

| Mức | Vai trò | Câu hỏi | Ví dụ |
|---|---|---|---|
| **Product Goal** | Định hướng trạng thái tương lai của sản phẩm | “Tại sao sản phẩm cần thay đổi?” | Tự phục vụ ghi danh và vào bài đúng quyền |
| **Sprint Goal** | Tập trung Scrum Team trong một Sprint | “Trong vòng ngắn này, bước tiến có ý nghĩa là gì?” | Ghi danh miễn phí và vào bài đầu đạt DoD |
| **Product Backlog** | Danh sách emergent, ordered những gì cần cho sản phẩm | “Những khả năng/rủi ro nào cần cân nhắc theo thứ tự?” | Ghi danh miễn phí, trạng thái PENDING, callback thanh toán |
| **Sprint Backlog** | Sprint Goal, các PBI được chọn và kế hoạch thực hiện | “Chúng ta dự định làm gì và điều chỉnh ra sao?” | Các PBI/lát cắt, test và công việc cần thiết |
| **Increment** | Một bước cụ thể hướng tới Product Goal, có thể sử dụng khi đạt DoD | “Điều gì thực sự hoạt động đúng?” | Luồng ghi danh được tích hợp và kiểm chứng |

Scrum hữu ích khi đội cần **liên kết liên tục** giữa năm câu hỏi trên thay vì làm từng yêu cầu rời rạc.

### 2.4. Mục tiêu không phải lời hứa không được học thêm

Trong Sprint, Scrum Team có thể học thêm về công việc. Scrum Guide quy định:

- Không thực hiện thay đổi làm **nguy hại Sprint Goal**.
- **Chất lượng không giảm**.
- Product Backlog được refinement khi cần.
- Phạm vi có thể được **làm rõ và thương lượng lại với Product Owner** khi có thêm hiểu biết.

Điều này khác “ngày đầu Sprint đã chốt mọi dòng code, mọi task và không ai được hỏi thêm”. **Tập trung vào mục tiêu** giúp đội thích ứng về cách đạt nó mà không thay đổi tùy tiện lý do tồn tại của Sprint.

### 2.5. Mục tiêu chung cần thẩm quyền quyết định

Một Sprint Goal không thể giúp nếu năm người quản lý giao công việc trái nhau và Product Owner không có quyền quản lý thứ tự Product Backlog.

Trong Scrum, Product Owner là **một người, không phải một ủy ban**, chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả; có thể ủy quyền tác vụ nhưng vẫn chịu trách nhiệm cuối. Developers chịu trách nhiệm tạo Increment có thể sử dụng và kế hoạch thực hiện; Scrum Master chịu trách nhiệm hiệu quả Scrum Team.

Nếu tổ chức giữ nguyên quyền phê duyệt nhiều cấp cho mọi quyết định thường ngày, **cần tháo ràng buộc quyền hạn** chứ không chỉ yêu cầu một Product Owner “quản lý stakeholder khéo hơn”.

## 3. Vì sao “nhịp kiểm tra định kỳ” là tín hiệu mạnh để cân nhắc Scrum?

Khi sản phẩm có độ bất định, một kế hoạch sáu tháng rất chi tiết thường dựa trên nhiều giả định chưa được kiểm chứng. Scrum tạo một **nhịp cố định ngắn** để đội vừa tạo Increment vừa có cơ hội thường xuyên kiểm tra mục tiêu và cách làm.

### 3.1. Sprint là nhịp chứa mọi hoạt động để tạo giá trị

Theo Scrum Guide 2020, Sprint có độ dài cố định **không quá một tháng**, diễn ra liên tiếp; Sprint mới bắt đầu ngay khi Sprint trước kết thúc. Nó chứa những công việc cần để đạt Product Goal, gồm **Sprint Planning, Daily Scrums, Sprint Review và Sprint Retrospective**.

Điểm quan trọng:

- Sprint không phải khoảng thời gian “chỉ được code”.
- Sprint không đòi mọi nhu cầu sản phẩm phải hoàn tất hết.
- Sprint không tự là một đợt phát hành duy nhất.
- Sprint không yêu cầu các stakeholder chờ tới cuối mới xem phần mềm; những Increment đáp ứng DoD có thể được cung cấp sớm hơn.
- Sprint tạo **tính dự đoán về cơ hội kiểm tra–thích ứng**, không tự bảo đảm mọi PBI ước lượng sẽ Done đúng ngày.

### 3.2. Timebox giúp giới hạn độ trễ của học tập

Giả sử:

~~~text
Lập kế hoạch chi tiết trong 3 tháng
    -> Xây 6 tuần
    -> Kiểm thử tích hợp 3 tuần
    -> Review người học lần đầu
~~~

Nếu giả định về trạng thái thanh toán sai, phát hiện có thể tới rất muộn.

Một nhịp ngắn hơn có thể:

~~~text
Product Goal: Học viên tự ghi danh và vào bài
    |
Sprint 1: Lát cắt ghi danh miễn phí đạt DoD
    -> Review kết quả, phản hồi người học
    |
Sprint 2: Trạng thái thanh toán đang xử lý đáng tin
    -> Review hành vi và vấn đề thực
    |
Sprint 3: Xác nhận thanh toán an toàn + quyền học
    -> Review, học và điều chỉnh tiếp
~~~

Đây là **lộ trình minh họa**, không phải lời hứa rằng ba Sprint luôn đủ hoặc mọi hệ thống đều cần xây luồng miễn phí trước. Ngay từ Sprint 1, Increment vẫn phải đạt DoD trong phạm vi đã chọn.

### 3.3. Sprint Review là kiểm tra sản phẩm, không phải duyệt báo cáo

Sprint Review nhằm kiểm tra **kết quả Sprint** và xác định sự thích ứng trong tương lai. Scrum Team trình bày những gì đã đạt hướng Product Goal; họ cùng stakeholders thảo luận tiến triển và điều gì cần làm tiếp, kể cả thay đổi môi trường/nhu cầu.

Một Review có chất lượng hỏi:

- Phần nào đã đạt DoD và thực sự sử dụng được?
- Mục tiêu Sprint đã đạt đến đâu?
- Người dùng hoặc stakeholder thấy điều gì khác với dự đoán?
- Điều kiện thị trường, pháp lý, vận hành hoặc phụ thuộc đã thay đổi không?
- Product Backlog nên điều chỉnh ra sao?

Nó **không phải gate phê duyệt phát hành**, một buổi demo slide cho quản lý hay chỉ điểm danh task. Nếu phần mềm đã sẵn sàng, không cần đợi Review mới được release; quyết định release tuân theo các chính sách thích hợp.

### 3.4. Sprint Retrospective là kiểm tra cách làm, không phải tìm người có lỗi

Retrospective tập trung tăng chất lượng và hiệu quả. Scrum Team xem cách làm trong Sprint, tương tác, quy trình, công cụ, DoD và những điều gây hiểu lầm; sau đó lên kế hoạch cải thiện.

Ví dụ:

> “Ba PBI bị chặn vì hợp đồng entitlement chưa rõ. Sprint tới chúng ta thử refinement bằng ví dụ cùng Product Owner, Developers và người có chuyên môn test; bổ sung consumer contract test ở CI; xem work item age và lỗi tích hợp sau thử.”

Kết quả tốt hơn câu “các nhóm cần giao tiếp nhiều hơn” nhưng không ai biết thay đổi cụ thể là gì.

### 3.5. Sprint Planning và Daily Scrum giữ nhịp gần mục tiêu

**Sprint Planning** làm rõ vì sao Sprint có giá trị, điều gì có thể hoàn tất và cách thực hiện. Scrum Team cùng tham gia; Product Owner đề xuất cách sản phẩm có thể tăng giá trị, Developers lựa chọn lượng công việc và lập kế hoạch.

**Daily Scrum** là event 15 phút cho **Developers** kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog. Nó không phải báo cáo cá nhân cho Scrum Master hay quản lý, dù các thành viên khác có thể hỗ trợ khi phù hợp.

Nếu mỗi Daily chỉ là “hôm qua tôi làm gì”, những item bị chặn không được tháo, thì đội chưa khai thác cơ chế **kiểm tra và thích ứng** dù event đã diễn ra đúng giờ.

### 3.6. Sprint dài bao nhiêu là hợp lý?

Scrum Guide giới hạn Sprint tối đa một tháng nhưng **không bắt buộc đúng hai tuần**. Lựa chọn độ dài nên xét:

| Tiêu chí | Sprint ngắn hơn có thể có ích khi... | Sprint dài hơn có thể cần cân nhắc khi... |
|---|---|---|
| Phản hồi người dùng | Có thể tạo và kiểm tra lát cắt nhỏ thường xuyên | Cần thêm thời gian để có evidence có ý nghĩa, dù vẫn nên kiểm tra sớm |
| Độ bất định | Giả thuyết và ưu tiên đổi nhanh | Mục tiêu tương đối ổn định nhưng vẫn cần vòng inspection |
| Khả năng tích hợp | CI/DoD cho phép Increment nhỏ | Năng lực chưa đủ, nhưng đây cũng là tín hiệu cần cải thiện kỹ thuật |
| Chi phí điều phối | Đội hưởng lợi từ cập nhật mục tiêu thường xuyên | Chi phí events tương đối cao so với độ dài Sprint |
| Phụ thuộc | Có thể xử lý contract/phụ thuộc từng lát cắt | Phụ thuộc dài cần được giảm hoặc làm rõ trước, không dùng Sprint dài để che |

**Đừng chọn Sprint dài chỉ để khỏi phải xử lý lỗi kiểm thử muộn**; cũng đừng rút Sprint xuống một tuần trong khi mỗi Increment vẫn phải chờ một tháng mới có thể dùng, rồi coi vấn đề đã giải quyết.

### 3.7. Nhịp kiểm tra không đồng nghĩa nhịp phát hành

Ba mốc cần tách:

1. **Done:** PBI/Increment đáp ứng Definition of Done.
2. **Released/deployed:** phần mềm được đưa tới môi trường/người dùng theo chính sách thích hợp.
3. **Outcome observed:** người dùng thực sự tạo kết quả, được đo/quan sát sau cung cấp.

Một Increment có thể đạt DoD mà chưa release; một phần mềm đã deploy cũng chưa chắc người dùng có quyền sử dụng hoặc đã đạt outcome. **Sprint Review không thay kiểm tra DoD hay quyết định release.**

## 4. Scrum Guide 2020: những gì thực sự được yêu cầu

Chọn Scrum phải dựa trên **khung Scrum thật**, không trên một phiên bản “Scrum” chỉ gồm các cuộc họp.

### 4.1. Cơ sở: empiricism và lean thinking

Scrum dựa trên empiricism (học từ kinh nghiệm, quyết định theo điều quan sát được) và lean thinking (giảm lãng phí, tập trung vào điều thiết yếu). Ba trụ cột của empiricism:

1. **Transparency — Minh bạch:** những gì quan trọng phải được thấy và có nghĩa chung.
2. **Inspection — Kiểm tra:** xem tiến triển và artifacts thường xuyên để phát hiện thay đổi/bất thường.
3. **Adaptation — Thích ứng:** điều chỉnh khi lệch khỏi giới hạn chấp nhận được hoặc có thông tin mới.

Năm giá trị Scrum là **Commitment, Focus, Openness, Respect và Courage**. Không có sự cởi mở về trạng thái và chất lượng, một dashboard đầy “Done” giả sẽ làm inspection mất giá trị.

### 4.2. Scrum Team và accountabilities

Scrum Team bao gồm **một Scrum Master, một Product Owner và Developers**; không có phân cấp hay sub-teams bên trong Scrum Team. Scrum Team **cross-functional** (cùng nhau có đủ kỹ năng tạo giá trị mỗi Sprint) và **self-managing** (tự quyết ai làm gì, khi nào và cách nào trong phạm vi phù hợp).

Scrum Guide 2020 mô tả Scrum Team thường **10 người hoặc ít hơn**. Đây là hướng dẫn thiết kế đội nhỏ, không phải KPI buộc mọi đội phải đúng số thành viên cố định; khi team trở nên quá lớn, cần cân nhắc tổ chức thành nhiều Scrum Teams gắn kết cùng product theo các quy tắc chung của Scrum.

| Accountability | Trách nhiệm cốt lõi | Không phải |
|---|---|---|
| **Product Owner** | Tối đa hóa giá trị sản phẩm; quản lý Product Backlog hiệu quả | Người chỉ viết ticket hoặc một hội đồng ưu tiên chia nhau accountability |
| **Developers** | Tạo mọi khía cạnh của Increment có thể sử dụng mỗi Sprint; lập Sprint Backlog và đáp ứng DoD | Chỉ code theo lệnh rồi bàn giao toàn bộ chất lượng cho QA cuối Sprint |
| **Scrum Master** | Chịu trách nhiệm hiệu quả Scrum Team; hỗ trợ thiết lập Scrum và cải tiến trong tổ chức | Người quản lý nhân sự/đọc status của từng Developer mỗi Daily |

Tên chức danh không đủ: **quyền ra quyết định và khả năng thực hiện trách nhiệm** phải có thật.

### 4.3. Artifacts và commitments

| Artifact | Commitment | Ý nghĩa |
|---|---|---|
| **Product Backlog** | **Product Goal** | Sắp thứ tự những gì cần để cải thiện sản phẩm; hướng tới mục tiêu sản phẩm |
| **Sprint Backlog** | **Sprint Goal** | Kế hoạch của Developers trong Sprint, hướng tới mục tiêu Sprint |
| **Increment** | **Definition of Done** | Phần sản phẩm có thể sử dụng, đạt chất lượng chung |

Không có cơ chế DoD tin cậy, Product Backlog “đã xử lý 90%” có thể chỉ là các mảnh code không sử dụng được. Không có Product Goal, Sprint có thể biến thành một tập ticket tùy tiện.

### 4.4. Những events trong Scrum

| Event | Mục đích | Timebox trong Scrum Guide 2020 |
|---|---|---|
| **Sprint** | Container cho các events, tạo Increment hướng tới Product Goal | Độ dài cố định, **một tháng hoặc ngắn hơn** |
| **Sprint Planning** | Vì sao Sprint có giá trị, làm gì, làm thế nào | Tối đa **8 giờ** cho Sprint một tháng; thường ngắn hơn nếu Sprint ngắn hơn |
| **Daily Scrum** | Developers kiểm tra Sprint Goal và điều chỉnh kế hoạch | **15 phút** |
| **Sprint Review** | Kiểm tra kết quả Sprint với stakeholders và thích ứng | Tối đa **4 giờ** cho Sprint một tháng; ngắn hơn nếu Sprint ngắn hơn |
| **Sprint Retrospective** | Lập kế hoạch cải thiện chất lượng và hiệu quả | Tối đa **3 giờ** cho Sprint một tháng; ngắn hơn nếu Sprint ngắn hơn |

Timebox là **giới hạn thời gian**, không phải mục tiêu phải dùng hết. Một Sprint Review 45 phút có kiểm tra sản phẩm và quyết định tốt có thể hữu ích hơn bốn giờ thuyết trình không có phản hồi.

### 4.5. Những điều không phải yêu cầu bắt buộc

Scrum Guide không quy định:

- Story points, Planning Poker hoặc velocity như KPI.
- Một phần mềm quản lý việc hay mẫu user story cụ thể.
- Scrum of Scrums hoặc lễ “grooming” với timebox chính thức.
- TDD, pair programming, CI/CD hay kiến trúc microservices bắt buộc.
- Mỗi Sprint phải release đúng một lần.
- Sprint Review là cửa phê duyệt release.
- Một người Scrum Master phải làm thư ký theo dõi task.
- Tất cả Scrum Teams cùng product phải có một **Sprint Goal giống hệt**; họ cần cùng Product Goal, Product Backlog, Product Owner và DoD khi cùng một sản phẩm.

Những thực hành bổ sung như user stories, TDD, Kanban flow metrics và khám phá sản phẩm có thể rất hữu ích. Điều cần làm là **phân biệt Scrum rule với lựa chọn cải tiến phù hợp bối cảnh**, không biến lựa chọn thành luật áp đặt cho mọi đội.

### 4.6. Scrum tối giản nhưng không tùy ý bỏ cấu phần rồi vẫn tuyên bố nguyên vẹn

Scrum là framework cố ý chưa hoàn chỉnh về kỹ thuật triển khai, nhưng **các cấu phần định nghĩa của nó có quan hệ với nhau**. Bỏ Sprint Goal hoặc DoD rồi chỉ giữ Daily và Planning không mang lại cùng cơ chế empiricism.

Nếu tổ chức chọn một quy trình lai vì bối cảnh thật, hãy **mô tả trung thực cách đang làm**, điểm nào theo Scrum, điểm nào khác; không cần tô nhãn để đạt điểm “đúng Scrum” nếu hệ thống không phù hợp. Nhưng nếu muốn áp dụng Scrum đầy đủ, phải hiểu và hỗ trợ các thành phần của nó.

## 5. Điều kiện thực tế để Sprint Goal và nhịp kiểm tra có hiệu quả

Quyết định chọn Scrum nên kiểm tra **khả năng thực thi**, không chỉ sở thích quản lý về lịch hai tuần.

### 5.1. Một sản phẩm và người dùng đủ rõ

Nếu “sản phẩm” chỉ là một nhóm API không biết ai dùng, Product Owner khó tối đa hóa giá trị. Cần làm rõ:

- Người dùng/khách hàng và stakeholders.
- Ranh giới sản phẩm.
- Giá trị muốn tạo và hậu quả nếu không đạt.
- Những điều kiện chất lượng, rủi ro và quy định áp dụng.
- Product Goal có thể dùng để chọn ưu tiên.

Scrum Guide định nghĩa sản phẩm là phương tiện cung cấp giá trị, có ranh giới rõ, stakeholders được biết và người dùng/khách hàng xác định. Một sản phẩm có thể là dịch vụ, sản phẩm vật lý hoặc thứ trừu tượng; **không suy sản phẩm từ số repository**.

### 5.2. Product Owner có khả năng ordering backlog

Nếu mọi stakeholder có quyền chèn việc trực tiếp vào Sprint, Sprint Goal bị đe dọa liên tục. Một Product Owner trên giấy nhưng không có quyền không giúp đội thích ứng.

Khi chọn Scrum cần:

1. Làm rõ ai chịu trách nhiệm Product Backlog.
2. Thống nhất cách đưa yêu cầu/rủi ro khẩn vào xem xét.
3. Có đường xử lý sự cố/pháp lý không thể trì hoãn.
4. Cho Developers không gian lập kế hoạch đạt Sprint Goal.
5. Minh bạch khi trade-off phạm vi và giá trị thay đổi.

### 5.3. Đội có thể giao một lát cắt đạt DoD

Nếu mọi PBI phải chuyển lần lượt qua UI → API → database → QA và chỉ tích hợp cuối quý, việc rút thời gian Sprint xuống hai tuần **không tự sinh Increment**.

Đội có thể cần:

- Kỹ năng cross-functional ở cấp Scrum Team.
- Lát cắt dọc đủ nhỏ có giá trị.
- Hợp đồng API/data và tích hợp sớm.
- CI, chiến lược test và môi trường phù hợp.
- DoD minh bạch và không bị hạ để kịp báo cáo.

**Scrum không bắt buộc XP**, nhưng những thực hành như TDD, pair programming, CI và refactoring có thể là điều kiện thực tế quan trọng để tạo Increment bền vững.

### 5.4. Stakeholders sẵn sàng học từ Increment

Sprint Review không đem lại nhiều giá trị nếu stakeholders:

- Chỉ muốn xem phần trăm task hoặc bản trình bày.
- Không sẵn sàng điều chỉnh thứ tự Product Backlog.
- Không thể cho phản hồi có ý nghĩa về khả năng sử dụng.
- Yêu cầu giữ nguyên mọi yêu cầu đã ký dù có bằng chứng mới.

Điều đó không có nghĩa mọi cam kết pháp lý hoặc hợp đồng đều được đổi tùy ý. Cần xác định **phạm vi linh hoạt**, cách quản lý thay đổi và quyền quyết định để phản hồi được chuyển thành hành động đúng.

### 5.5. Công việc không liên tục làm mục tiêu mất ý nghĩa

Scrum vẫn có thể xử lý lỗi khẩn, hỗ trợ hoặc thay đổi mới, nhưng nếu **hầu hết năng lực** mỗi ngày dành cho incident không dự đoán được, đội sẽ khó bảo vệ Sprint Goal có giá trị.

Trước khi chọn Scrum, cần hỏi:

- Tỷ lệ công việc planned/unplanned là bao nhiêu, tính trong nhiều kỳ?
- Việc khẩn đến theo chính sách dịch vụ hay chỉ do ưu tiên mơ hồ?
- Có thể tách luồng incident/support khỏi luồng phát triển sản phẩm không?
- Có thể dành một phần năng lực hợp lý cho Sprint Goal không?
- Nếu không, dùng Kanban để kiểm soát WIP, age, expedite và service outcomes có phù hợp hơn?

**Không có ngưỡng phần trăm unplanned work phổ quát** để quyết định Scrum thất bại. Cần xét tính chất dịch vụ, mức gián đoạn, khả năng tạo Increment và mục tiêu của đội.

## 6. Khung ra quyết định: Scrum có giải quyết đúng điểm nghẽn không?

Một bảng so sánh giúp đội tránh tranh luận “tôi thích Sprint hơn”, nhưng đừng biến nó thành thuật toán chấm điểm giả chính xác. **Chọn cách tiếp cận là quyết định theo bối cảnh và giả thuyết**, cần được kiểm tra bằng công việc và phản hồi thật.

### 6.1. Bảy câu hỏi chẩn đoán

| Trục đánh giá | Câu hỏi | Tín hiệu nghiêng về Scrum | Tín hiệu cần cân nhắc cách khác hoặc cải thiện điều kiện |
|---|---|---|---|
| **Giá trị** | Có một sản phẩm với mục tiêu đủ thống nhất? | Có Product Goal có thể điều hướng thứ tự | Chủ yếu là các request rời rạc của nhiều dịch vụ độc lập |
| **Dòng công việc** | Đội phát triển khả năng sản phẩm hay phản ứng với việc khẩn? | Phần đáng kể năng lực dành cho tăng trưởng/đổi sản phẩm theo mục tiêu | Incident/support không dự báo được là dịch vụ chính |
| **Nhịp học** | Stakeholders có thể kiểm tra kết quả theo chu kỳ ngắn? | Review mỗi Sprint giúp đổi lựa chọn có ý nghĩa | Chỉ báo cáo trạng thái, không có quyền hoặc dữ liệu phản hồi |
| **Increment** | Có thể hoàn tất lát cắt dùng được theo DoD? | Có năng lực tích hợp/kiểm chứng trong Sprint | “Done” chỉ là code complete, QA chờ cuối quý |
| **Accountabilities** | Ai sở hữu giá trị và backlog? | Product Owner thực quyền; Developers tự quản | Nhiều người ra lệnh ưu tiên trái nhau |
| **Phụ thuộc** | Đội kiểm soát được đủ điều kiện để đạt Sprint Goal? | Phụ thuộc làm rõ sớm, có cách tích hợp | Mọi việc phải đợi một hệ thống/phê duyệt ngoài quyền nhiều tuần |
| **Đo lường** | Có bằng chứng về kết quả và cách làm để inspect/adapt? | Increment/flow/outcome có thể quan sát, chất lượng minh bạch | Chỉ có velocity và tổng giờ làm, không có dữ liệu Done |

**Cách dùng:** thảo luận bằng ví dụ thật, ghi giả định và điều kiện còn thiếu. Một dấu hiệu đỏ không luôn đồng nghĩa “không dùng Scrum”, nhưng nếu nhiều điều kiện nền tảng đều chưa có, triển khai nghi thức trước dễ trở thành **Scrum trên giấy**.

### 6.2. Ba kết luận lựa chọn có thể hợp lý

**Kết luận A — Nên thử Scrum:** đội làm một sản phẩm, cần Product Goal và các Sprint Goals để tập trung, có Increment nhỏ và stakeholders có thể cùng inspect/adapt. Các ràng buộc accountabilities và DoD khả thi.

**Kết luận B — Scrum có triển vọng nhưng phải cải thiện nền tảng:** sản phẩm và mục tiêu rõ nhưng chưa thể tích hợp thường xuyên; hoặc Product Owner thiếu quyền, nhóm bị chia theo tầng. Cần giải quyết ràng buộc **trước/đồng thời với pilot**, không lấy Scrum events làm “cơ chế chữa” thiếu test hoặc quyền.

**Kết luận C — Cách phối hợp khác phù hợp hơn hiện tại:** đội chủ yếu cung cấp dịch vụ vận hành liên tục, nhiều việc khẩn đến theo thời gian thực, ưu tiên do policy và service level chi phối, một Sprint Goal ổn định ít có ý nghĩa. Kanban với Definition of Workflow, WIP, expedite, work item age và service review có thể rõ hơn. Nếu điều kiện thay đổi, kết luận có thể đổi.

### 6.3. Decision tree minh họa

~~~mermaid
flowchart TD
    A["Câu hỏi: sản phẩm/giá trị cần giao là gì?"] --> B{"Có product boundary và mục tiêu đủ rõ?"}
    B -->|"Chưa"| C["Làm rõ người dùng, outcome, quyền ưu tiên trước"]
    B -->|"Có"| D{"Công việc hướng mục tiêu có thể tạo Increment ngắn hạn?"}
    D -->|"Không"| E["Phân tích phụ thuộc, DoD, CI, team boundary"]
    D -->|"Có"| F{"Cần nhịp Sprint để cùng inspect/adapt?"}
    F -->|"Có"| G["Cân nhắc pilot Scrum đầy đủ và phù hợp bối cảnh"]
    F -->|"Không hoặc luồng khẩn chi phối"| H["Cân nhắc Kanban/pull policies và service feedback"]
    E --> I{"Khắc phục điều kiện trong phạm vi thử?"}
    I -->|"Có"| G
    I -->|"Chưa"| J["Giảm WIP, giảm rủi ro kỹ thuật và tạo năng lực trước"]
    G --> K["Đo Increment, Sprint Goal, chất lượng, flow, outcome"]
    H --> L["Đo service outcome, WIP, age, throughput, cycle time"]
    K --> M["Inspect & Adapt: giữ, sửa hoặc chọn cách khác"]
    L --> M
    M -. "Thông tin mới" .-> A
~~~

Decision tree **không thay trách nhiệm quyết định của người thật**. Nó nhằm buộc người chọn Scrum kiểm tra *lý do dùng Sprint*, thay vì chỉ chọn một tên framework.

### 6.4. Khi nào mục tiêu chung có giá trị hơn tập trung theo loại yêu cầu?

Ví dụ một product team có 12 yêu cầu:

- 4 việc cải thiện trạng thái ghi danh.
- 3 việc bảo vệ callback và quyền học.
- 2 việc nâng test integration.
- 3 việc làm banner và sửa nội dung ít liên quan.

Nếu Sprint Goal là **“tạo một lát cắt ghi danh đáng tin”**, đội có cơ sở chọn những việc hỗ trợ mục tiêu, thương lượng phạm vi và giảm WIP. Nếu nhóm chỉ nhận việc từ một queue theo thứ tự đến mà không xem quan hệ giá trị, có thể hoàn tất banner trước khi sửa lỗi quyền quan trọng.

Ngược lại, một đội chuyên xử lý ticket vận hành cho 20 hệ thống không thể ép 12 yêu cầu rời rạc thành một Sprint Goal sản phẩm có nghĩa chỉ để “dùng Scrum”. Nên xác định **dạng dịch vụ thực tế**.

### 6.5. Nhu cầu “họp đều” chưa đủ để chọn Scrum

Một nhóm có thể chỉ muốn:

- Báo cáo tiến độ vào thứ Sáu.
- Có cuộc họp tuần để giải quyết blocker.
- Tổ chức demo tháng một lần cho quản lý.

Những nhu cầu ấy có thể được đáp ứng **không cần toàn bộ Scrum framework**. Cần chọn Scrum khi mối liên hệ giữa **mục tiêu, Increment, nhịp kiểm tra và thích ứng** giúp tạo giá trị, không chỉ khi tổ chức muốn một lịch họp thống nhất.

## 7. Scrum và Kanban: nhịp timebox khác quản lý dòng công việc liên tục

Trong lựa chọn cách tiếp cận, Scrum và Kanban thường bị mô tả đơn giản quá mức là “Scrum có Sprint; Kanban không có Sprint”. Mô tả này bỏ qua các cơ chế chính: **Scrum tổ chức mục tiêu và inspection qua Sprint; Kanban định nghĩa, trực quan hóa, quản lý và cải thiện flow**.

### 7.1. Cơ chế và câu hỏi mà từng cách nhấn mạnh

| Tiêu chí | Scrum | Kanban |
|---|---|---|
| **Đối tượng tổ chức chính** | Scrum Team tạo Increment cho Product Goal trong các Sprints | Dòng công việc/dịch vụ có Definition of Workflow rõ |
| **Mục tiêu ngắn hạn** | Sprint Goal — một commitment của Sprint Backlog | Chính sách dịch vụ và mục tiêu về flow/outcome; Kanban Guide không bắt một Sprint Goal |
| **Nhịp làm việc** | Sprints cố định một tháng hoặc ngắn hơn; events inspect/adapt | Công việc có thể kéo liên tục, feedback theo chính sách/nhu cầu |
| **Ưu tiên** | Product Owner quản lý Product Backlog cho Scrum product | Tùy thiết kế dịch vụ và quyền quyết định của tổ chức |
| **Chất lượng** | Increment cần Definition of Done | Workflow cần điểm Finished và các policy; chất lượng phải được xác định phù hợp |
| **Flow metrics** | Có thể dùng thêm để hiểu tiến triển | Bốn metrics tối thiểu: WIP, throughput, work item age, cycle time |
| **Đổi ưu tiên liên tục** | Cần bảo vệ Sprint Goal, thương lượng scope khi học thêm | Có thể pull/đổi thứ tự theo policy, capacity, class of service |
| **Rủi ro khi hiểu sai** | Sprint thành mini-waterfall hoặc KPI points | Bảng là task tracker, không quản WIP hay chất lượng |

Không nên nói Kanban **“không có mục tiêu”** hoặc Scrum **“không quản lý flow”**. Mọi cách tiếp cận đều cần kết nối với giá trị và khả năng học; khác nhau ở **cấu trúc và chính sách mặc định**.

### 7.2. Ví dụ team nền tảng với công việc không dự đoán được

Một nhóm platform vận hành hệ thống CI/CD và nhận:

- Sự cố runner không chạy.
- Yêu cầu tạo môi trường.
- Tăng dung lượng tài nguyên.
- Nâng phiên bản pipeline.
- Giải quyết sự cố bảo mật theo mức độ ưu tiên.

Một Sprint Goal “hoàn thành 15 tickets” dễ bị thay thế bởi yêu cầu khẩn. Nếu mục tiêu chính là **khả năng đáp ứng dịch vụ** chứ không phải một Increment sản phẩm có phạm vi ngắn hạn, nhóm có thể dùng Kanban:

~~~text
Requested -> Ready -> In Progress -> Verification -> Done
                    |
                    +-- Blocked: hiện rõ age và owner

Policies:
  - Pull khi có capacity.
  - WIP limit ở các bước đang xử lý.
  - Incident khẩn theo class-of-service đã công bố.
  - Không coi ticket Done khi chưa đạt điều kiện an toàn.
  - Service review định kỳ dựa trên age, throughput, quality, outcome.
~~~

Điều này không cấm nhóm platform phát triển những năng lực mới qua các mục tiêu theo thời gian. **Kanban không ngăn mục tiêu hay reviews định kỳ**; nó không yêu cầu cấu trúc Sprint/commitments của Scrum.

### 7.3. Khi Scrum và Kanban bổ sung nhau

Một Scrum Team có thể gặp:

- Sprint Goal rõ nhưng quá nhiều PBI đang dở.
- Nhiều item chờ review hoặc test tích hợp.
- Work item age dài nhưng dashboard chỉ hiện story points hoàn tất.

Đội có thể dùng thực hành Kanban để:

1. Định nghĩa workflow của PBI từ Started tới Done.
2. Trực quan hóa WIP và blocked.
3. Kiểm soát WIP để giúp item tiến tới Done.
4. Theo dõi age để xử lý công việc già trước khi kéo thêm.
5. Sử dụng throughput/cycle time lịch sử hỗ trợ dự báo với giới hạn rõ.
6. Quan sát những điểm nghẽn trong Retrospective.

Khi đã dùng Scrum, các thực hành này **không thay Product Goal, Sprint Goal hoặc Scrum events**, mà làm minh bạch dòng công việc giúp đạt Sprint Goal.

### 7.4. Không gắn nhãn “Scrumban” để tránh định nghĩa điều mình làm

Một đội có thể kết hợp nhịp Sprint với chính sách WIP, hoặc chọn Kanban và review sản phẩm định kỳ. Tên “Scrumban” đôi khi được dùng để mô tả nhiều cấu hình khác nhau; bản thân tên không xác định:

- Ai quyết định ưu tiên.
- Có Sprint Goal/DoD không.
- Làm gì khi có việc khẩn.
- WIP được tính thế nào.
- Khi nào kiểm tra outcome và chất lượng.

Hãy **mô tả policy và accountabilities cụ thể** thay vì dùng nhãn lai làm bằng chứng rằng cách làm đúng.

### 7.5. Một lỗi suy luận thường gặp

> “Đội có Kanban board trong Sprint, vậy chúng ta đang dùng Kanban thay vì Scrum.”

Không đúng chỉ từ công cụ. Một bảng trạng thái không tự cho biết Definition of Workflow, explicit policies và flow measurement. Tương tự, việc chia công việc thành hai tuần trên một công cụ không tự là Scrum nếu thiếu Scrum Team, goal, Increment, DoD và events.

## 8. XP và kỹ thuật: điều kiện giúp Scrum tạo Increment có chất lượng

Scrum cố ý không mô tả đầy đủ cách viết code và kiểm thử. Chọn Scrum mà không đầu tư năng lực kỹ thuật có thể dẫn tới **một vòng Sprint chỉ chốt báo cáo thay vì sản phẩm sử dụng được**.

### 8.1. Các thực hành XP đáng cân nhắc

| Thực hành | Tác dụng cho Sprint và Increment | Điều cần tránh |
|---|---|---|
| **Test-Driven Development (TDD)** | Phản hồi nhanh về hành vi/thiết kế ở lớp phù hợp | Đếm unit tests thay vì kiểm tra rủi ro thật |
| **Continuous Integration (CI)** | Tích hợp thay đổi nhỏ sớm, tránh dồn xung đột cuối Sprint | Build xanh nhưng hợp đồng hoặc môi trường production khác xa |
| **Pair programming** | Chia sẻ tri thức, giải quyết thiết kế phức tạp | Áp 100% không xét mục đích hoặc năng lực |
| **Refactoring** | Giữ code có thể thay đổi theo feedback | Viết lại kiến trúc không có mục tiêu/rủi ro |
| **Simple design** | Giảm độ phức tạp không cần thiết, giúp slicing | Lược bỏ yêu cầu bảo mật và khôi phục quan trọng |
| **Small releases** | Rút ngắn thời gian học từ sản phẩm thực | Release nhanh hơn khả năng kiểm chứng/giảm rủi ro |
| **Collective ownership** | Giảm bàn giao và phụ thuộc cá nhân | Bỏ review/ownership dữ liệu và contract |
| **Khách hàng tham gia thường xuyên** | Làm rõ hành vi, nhận phản hồi nhanh | Chỉ hỏi ý kiến mà không kiểm tra người dùng thật |

Những thực hành này **có thể dùng với Scrum hoặc Kanban**. Scrum Guide không bắt buộc TDD/CI, nhưng **Definition of Done và Increment có thể sử dụng** đòi đội chọn cách kỹ thuật đủ mạnh theo bối cảnh.

### 8.2. Ví dụ PBI tưởng Done nhưng chưa đáp ứng DoD

~~~text
ENR-31: Trang thai thanh toan

UI done          : Co
API merged       : Co
Unit tests pass  : Co
Contract test    : Fail vi provider tra PENDING_AUTHORIZATION
Entitlement test : Chua co
Security review  : Chua xac minh theo rui ro
Increment usable : Chua du bang chung
~~~

Không thể kết luận PBI thuộc Increment Done chỉ vì ba dòng đầu xanh. Đội cần làm rõ contract/trạng thái, xử lý lỗi, kiểm chứng chất lượng theo DoD trước khi gọi Done.

### 8.3. Nếu chưa có CI, có nên hoãn Scrum?

Không có câu trả lời phổ quát. Cần xét:

- Có khả năng kiểm chứng Increment bằng biện pháp phù hợp khác trong phạm vi nhỏ không?
- Mức rủi ro nếu kiểm thử chậm hoặc thủ công là gì?
- Có thể đầu tư **một pipeline tối thiểu đáng tin** trong pilot Scrum không?
- Có thể chọn lát cắt nhỏ hơn để giữ DoD mà không “đẩy QA qua Sprint sau” không?
- Nếu các team vẫn không thể tích hợp trong một tháng, trở ngại nằm ở kỹ thuật hay ranh giới tổ chức?

Câu trả lời hợp lý có thể là **pilot Scrum cùng cải tiến engineering**, không phải “Scrum tự thay test” hay “đợi hệ thống kỹ thuật hoàn hảo rồi mới học Scrum”.

### 8.4. BDD, Specification by Example và hành vi thật

Một cuộc thảo luận ba góc nhìn nghiệp vụ, phát triển và kiểm thử có thể đưa ra ví dụ:

~~~gherkin
Feature: Hoc vien vao bai sau ghi danh

  Scenario: Ghi danh mien phi hop le
    Given hoc vien A du dieu kien ghi danh khoa K
    When A hoan tat yeu cau ghi danh
    Then he thong ghi nhan ghi danh hop le
    And A co quyen vao bai dau cua K

  Scenario: Thanh toan chua duoc xac nhan
    Given don D dang cho xac nhan tu nguon dang tin
    When hoc vien A mo bai thuoc don D
    Then he thong khong cap quyen nhu da thanh toan
    And giao dien hien thi trang thai trung thuc
~~~

Các ví dụ này giúp làm rõ Sprint Backlog và DoD. **Đặc tả Gherkin không tự là bằng chứng test đã chạy**; cần triển khai test, dữ liệu, môi trường và assertions.

### 8.5. Engineering có thể làm Sprint Goal linh hoạt hơn

Khi code có test/contract rõ, Developers có thể đổi cách triển khai giữa Sprint với chi phí thấp hơn, ví dụ:

- Đổi giải pháp UI dựa trên feedback về trạng thái PENDING.
- Chia một PBI lớn thành lát cắt nhỏ hơn không giảm điều kiện chất lượng.
- Phát hành giới hạn khả năng đã Done, tiếp tục kiểm chứng phương thức khác.
- Refactor trước khi mở rộng để tránh nhân đôi logic quyền.

**Sprint Goal giữ định hướng**; kỹ thuật tốt làm nhiều phương án đạt mục tiêu trở nên khả thi và an toàn hơn.

## 9. Những bối cảnh Scrum có thể kém phù hợp hoặc cần điều chỉnh điều kiện

Không nên kết luận “Scrum thất bại” chỉ vì đội có công việc khẩn, chuyên môn sâu hoặc hệ thống lớn. Cần xem **vì sao Sprint Goal, Increment và inspection cadence có hoặc không tạo tác dụng**.

### 9.1. Incident response và vận hành 24/7

**Đặc điểm:**

- Request không thể dự báo chính xác từng ngày.
- Ưu tiên theo mức nghiêm trọng và service level.
- Dừng xử lý sự cố để “giữ Sprint Goal” có thể nguy hiểm.

**Lựa chọn có thể phù hợp:** Kanban với classes of service, WIP, expedite, observability, incident review và các mục tiêu cải thiện reliability theo thời gian.

**Khi Scrum vẫn có chỗ:** một nhóm riêng hoặc một phạm vi capacity ổn định đang xây năng lực vận hành mới (tự động hóa, migration) và có Increment sản phẩm/dịch vụ để review mỗi Sprint.

Không nhất thiết tách team theo cơ học; có thể cần tổ chức ca trực/on-call và năng lực bảo vệ Sprint Goal. Quyết định theo tình trạng thật, không ép cùng cadence cho mọi loại việc.

### 9.2. Đội xử lý hàng loạt yêu cầu nhỏ độc lập

Ví dụ một nhóm hỗ trợ cấu hình các báo cáo cho nhiều đơn vị, mỗi yêu cầu là một dịch vụ nhỏ với thời hạn và chính sách đã rõ.

Nếu không có một mục tiêu sản phẩm gắn kết đủ để dẫn dắt Sprint Goal, Scrum có thể chỉ tạo batch “ticket tuần này”. Kanban giúp nhìn **request → delivery**, WIP, age và mức dịch vụ rõ hơn.

Nếu những yêu cầu lặp tiết lộ một sản phẩm cần phát triển (self-service dashboard), tổ chức có thể hình thành **Product Goal và một nhóm phát triển sản phẩm**, khi đó Scrum có thể đáng thử cho phần năng lực mới.

### 9.3. Nghiên cứu khám phá rất bất định

Một nhóm đang tìm hiểu liệu người học có cần công cụ ghi chú AI trong khóa học không, chưa rõ hành vi, rủi ro dữ liệu hoặc cách tạo giá trị.

Có thể dùng vòng thực nghiệm nhỏ theo thời gian, kể cả Scrum nếu:

- Có Product Goal có ý nghĩa.
- Có thể tạo Increment đáng kiểm chứng trong mỗi Sprint.
- Không biến giả thuyết chưa biết thành cam kết tính năng giả.
- Có guardrails về dữ liệu và người dùng.

Nếu công việc chủ yếu là nghiên cứu không thể tạo Increment phần mềm có thể sử dụng trong ngắn hạn, các **vòng discovery có mục tiêu và evidence riêng** có thể phù hợp hơn việc tự nhận mọi prototype là Increment Done.

### 9.4. Sản phẩm có ràng buộc pháp lý/kiểm định

Y tế, tài chính, giáo dục có dữ liệu cá nhân, thiết bị vật lý hoặc hệ thống an toàn cao có thể yêu cầu kiểm định và bằng chứng dài hạn. Scrum **không cho phép bỏ quy định** để giao phần mềm nhanh.

Cách tiếp cận hữu ích:

- Xác định DoD và điều kiện kiểm chứng theo rủi ro/chuẩn tổ chức.
- Tách được lát cắt nhỏ có ý nghĩa và evidence liên tục nơi khả thi.
- Làm rõ phần nào có thể inspect mỗi Sprint, phần nào cần hoạt động ngoài Sprint.
- Phân biệt Increment kỹ thuật đủ tiêu chuẩn của phạm vi với quyền/phê duyệt phát hành ra thị trường.
- Không “đánh dấu Done” các hạng mục không đạt chuẩn bắt buộc.

Nếu mỗi thay đổi cần một chu kỳ thử nghiệm bên ngoài dài không thể chia, **nhịp Sprint không tự rút ngắn chu kỳ đó**. Có thể cần kế hoạch nhiều tầng kết hợp công việc Agile nơi phù hợp và ràng buộc kiểm định thực.

### 9.5. Phụ thuộc nhà cung cấp bên ngoài không kiểm soát

Ví dụ sản phẩm ghi danh cần callback từ đối tác, nhưng sandbox chưa sẵn sàng trong nhiều tuần.

Đừng đưa việc “hoàn tất thanh toán qua đối tác B” vào Sprint Goal như thể team kiểm soát được, rồi đổ lỗi Developers khi đối tác không phản hồi.

Hướng xử lý:

- Xác định phần có thể hoàn tất và kiểm chứng độc lập.
- Làm rõ contract và rủi ro bên ngoài sớm.
- Có spike hoặc stub/mock với contract để học, **nhưng không gọi mock là xác nhận tích hợp thực**.
- Xem lại Sprint Goal và phạm vi theo quyền/khả năng thực.
- Nếu phụ thuộc chi phối toàn bộ dòng, cân nhắc flow policies và kế hoạch dịch vụ phù hợp.

### 9.6. Nhiều sản phẩm nhưng ép vào một backlog vì “Scrum”

Một nhóm platform phục vụ năm sản phẩm; các yêu cầu có người dùng và outcome khác nhau. Ép tất cả thành **một Product Backlog chung** chỉ vì muốn Scrum có thể tạo tranh chấp ưu tiên.

Nếu thực sự là **nhiều Scrum Teams cùng một sản phẩm**, Scrum Guide yêu cầu cùng Product Goal, Product Backlog, Product Owner và Definition of Done. Nhưng khi có **nhiều sản phẩm độc lập**, cần xác định product boundaries và service contracts, không áp nhầm quy tắc “một product” lên toàn công ty.

### 9.7. Đội không có quyền tự quản

Nếu mỗi task phải được quản lý phê duyệt, Daily Scrum chỉ là báo cáo, Product Owner không được ưu tiên và Developers không thể điều chỉnh kế hoạch, **nền tảng Scrum bị thiếu**.

Đội có thể thử cải thiện quyền một phần có kiểm soát:

1. Product Owner quản lý thứ tự một Product Backlog trong phạm vi rõ.
2. Developers tự chọn cách thực hiện/điều chỉnh kế hoạch để đạt Sprint Goal.
3. Guardrails về bảo mật/tuân thủ được công bố để đội tự quyết trong phạm vi an toàn.
4. Chỉ escalation khi quyết định vượt quyền.

Không cần trao quyền tùy tiện bỏ mọi kiểm soát, nhưng cũng không thể gọi một quy trình quản lý vi mô là Scrum chỉ vì dùng các tên event.

## 10. Thiết kế Product Goal và Sprint Goal đủ rõ để tạo tập trung

Mục tiêu yếu là một nguyên nhân khiến Scrum biến thành “chạy ticket hai tuần”. Để chọn Scrum có căn cứ, cần thử **viết và dùng mục tiêu trên một luồng sản phẩm thật**, không chỉ kiểm tra đội đã ghi mục “Sprint Goal” trong công cụ hay chưa.

### 10.1. Phân biệt mục tiêu, đầu ra và biện pháp

| Phát biểu | Phân loại | Vấn đề hoặc giá trị |
|---|---|---|
| “Nâng 5 services lên Java mới” | Đầu ra/thay đổi kỹ thuật | Có thể cần để bảo vệ hệ thống, nhưng cần nêu giá trị/rủi ro |
| “Hoàn tất 18 tickets” | Khối lượng công việc | Không nói mục tiêu nào cần đạt |
| “Tỷ lệ người học ghi danh hợp lệ và vào bài đầu tốt hơn” | Outcome định hướng | Cần định nghĩa cohort/cửa sổ, guardrails và tác động |
| “Cho phép ghi danh miễn phí end-to-end, đúng quyền trong luồng chuẩn” | Sprint Goal có khả năng kiểm chứng | Tạo một Increment nhỏ có ý nghĩa |
| “Tạo khả năng self-service ghi danh và vào học an toàn cho học viên đủ điều kiện” | Product Goal định hướng | Cho phép nhiều Sprint tạo tiến triển |
| “Giảm thời gian chờ integration bằng contract tests và self-service environment” | Mục tiêu cải thiện hệ thống | Hữu ích nếu có liên hệ tới khả năng giao Increment và quality |

Một mục tiêu không cần bắt buộc có dạng KPI chính xác. Khi dữ liệu còn thiếu, có thể đặt **mục tiêu khả năng sản phẩm** kèm bằng chứng nghiệm chứng và giả thuyết cần học.

### 10.2. Năm yếu tố của Sprint Goal hữu ích

1. **Giá trị hoặc rủi ro cụ thể:** người dùng/đội cần kết quả nào?
2. **Trọng tâm chung:** có đủ rõ để Developers biết điều gì phục vụ mục tiêu và điều gì không?
3. **Khả năng kiểm chứng:** làm sao biết hành vi/capability đã hoạt động?
4. **Không cứng cách làm:** có nhiều lựa chọn thực hiện để đội thích ứng khi phát hiện điều mới?
5. **Tương thích DoD và Sprint length:** có thể tạo Increment đúng chất lượng trong thời gian thực?

Ví dụ:

> **“Học viên đủ điều kiện ghi danh khóa miễn phí và truy cập bài đầu từ trang đăng ký một cách an toàn.”**

Khi gặp trở ngại UI framework, đội có thể đổi cách thiết kế giao diện nhưng vẫn đạt hành vi. Nếu thử nghiệm cho thấy yêu cầu ghi danh miễn phí chưa có ý nghĩa vì sản phẩm chỉ bán khóa trả phí, mục tiêu cần được xem lại từ thực tế sản phẩm **trước khi dùng làm cam kết**.

### 10.3. Từ Product Goal tới lát cắt Sprint

~~~mermaid
flowchart TD
    P["Product Goal:<br/>Học viên tự ghi danh và vào bài đúng quyền"]
    P --> B["Product Backlog theo giá trị và rủi ro"]
    B --> S1["Sprint Goal A:<br/>Ghi danh miễn phí end-to-end"]
    B --> S2["Sprint Goal B:<br/>Trạng thái PENDING rõ và đúng"]
    B --> S3["Sprint Goal C:<br/>Một phương thức thanh toán được xác thực"]
    S1 --> I1["Increment A đạt DoD"]
    S2 --> I2["Increment B đạt DoD"]
    S3 --> I3["Increment C đạt DoD"]
    I1 --> F["Review, feedback, dữ liệu sử dụng"]
    I2 --> F
    I3 --> F
    F -. "Cập nhật thứ tự theo bằng chứng" .-> B
~~~

Đây là minh họa **một chuỗi lựa chọn có thể có**, không phải ba Sprint phải thực hiện đúng theo lịch cố định. Product Owner có thể thay thứ tự dựa vào phản hồi, mức rủi ro hoặc yêu cầu mới.

### 10.4. Một Sprint Goal không nên gộp quá nhiều mục tiêu độc lập

**Yếu:**

> “Ghi danh miễn phí, tối ưu dashboard doanh thu, sửa UI trang blog và đổi thư viện UI.”

Bốn việc ít liên quan khiến khó biết điều gì đáng ưu tiên khi có biến động.

**Tốt hơn:**

> “Học viên đủ điều kiện tự ghi danh và vào bài đầu qua một lát cắt đơn giản đạt DoD.”

Nếu việc nâng thư viện UI thật sự là ràng buộc để đạt mục tiêu, nó có thể nằm trong kế hoạch kỹ thuật. Nếu không, Product Owner và Developers cần cân nhắc thứ tự khác hoặc dành năng lực cho công việc cần thiết theo thỏa thuận, thay vì làm mờ Sprint Goal.

### 10.5. Một Sprint Goal không đồng nghĩa cố định tất cả PBI

Giả sử Sprint Goal là “Học viên thấy trạng thái PENDING đáng tin”, nhưng trong Sprint đội phát hiện cần thay contract entitlement. Các Developers có thể:

- Làm rõ PBI đã chọn.
- Điều chỉnh cách thực hiện.
- Thương lượng phạm vi với Product Owner khi học thêm.
- Ưu tiên hoạt động cần thiết để đạt Sprint Goal và DoD.

Điều không được làm là **âm thầm đổi Sprint Goal thành “hoàn tất bao nhiêu ticket cũng được”**, hoặc bỏ những điều kiện chất lượng quan trọng để tuyên bố đã đạt mục tiêu.

### 10.6. Một Sprint Goal không có nghĩa mỗi ngày không được có việc khác

Trong thực tế, Scrum Team có thể dành năng lực xử lý lỗi hỗ trợ, bảo trì hoặc hoạt động cần thiết không trực tiếp là một phần rõ của Sprint Goal. Điều quan trọng là không để chúng **phá sự tập trung và làm Sprint Goal không còn ý nghĩa**.

Nếu việc khẩn xuất hiện thường xuyên, đội có thể:

1. Phân tích loại việc và mức ảnh hưởng.
2. Minh bạch năng lực đã bị tiêu tốn cho việc khẩn.
3. Thỏa thuận cách xử lý/ưu tiên trong điều kiện hợp lệ.
4. Cân nhắc tách service flow hoặc bổ sung Kanban policies.
5. Nếu không thể bảo vệ mục tiêu, xem lại **lý do chọn Scrum**.

Không có quy tắc bắt buộc mọi giờ trong Sprint phải được dùng cho đúng một Sprint Goal, nhưng **Scrum Team phải thực sự có commitment tập trung vào mục tiêu đó**.

### 10.7. Trường hợp không đạt Sprint Goal

Một Sprint Goal không đạt **không tự là bằng chứng Scrum không phù hợp**. Nó là thông tin quan trọng để kiểm tra:

- Sprint Goal có quá nhiều điều không kiểm soát được?
- PBI quá lớn hoặc không có lát cắt đủ nhỏ?
- Kiểm thử tích hợp/DoD bị đẩy muộn?
- Product Owner, Developers và stakeholders hiểu khác nhau về kết quả?
- Có việc khẩn thật làm mất năng lực?

Đội cần **minh bạch Increment nào đạt DoD** và học từ nguyên nhân. Không được đánh dấu PBI chưa Done thành Done hoặc viết lại mục tiêu sau khi Sprint kết thúc chỉ để báo cáo thành công.

### 10.8. Ai được hủy Sprint?

Theo Scrum Guide 2020, **Product Owner có thẩm quyền hủy Sprint** nếu **Sprint Goal trở nên lỗi thời**. Điều này khác hủy Sprint vì đội cảm thấy chậm, velocity thấp hoặc cần làm một tính năng mới hấp dẫn hơn.

Khi thấy Sprint Goal có thể lỗi thời, Scrum Team phải đánh giá thông tin và bối cảnh. Hủy Sprint là quyết định có chi phí; các PBI chưa Done được xem xét lại phù hợp. Đừng biến khả năng hủy Sprint thành cơ chế đổi toàn bộ kế hoạch mỗi ngày.

## 11. Một Sprint có mục tiêu và nhịp kiểm tra vận hành như thế nào?

Một người học thường hiểu Scrum event qua định nghĩa nhưng chưa hình dung **dòng công việc trước–trong–sau Sprint**. Dưới đây là mẫu hai tuần trên một Scrum product; timebox hai tuần là lựa chọn minh họa.

### 11.1. Trước Sprint: duy trì Product Backlog và làm rõ PBI

Trong quá trình phát triển sản phẩm, Product Owner và Developers liên tục thảo luận những PBI sắp làm:

- Vấn đề người dùng và mục tiêu.
- Giá trị, rủi ro và phụ thuộc.
- Acceptance examples và quality guardrails.
- Khả năng chia lát cắt theo hành vi.
- Kỹ năng và môi trường cần thiết.
- Bằng chứng để biết một phần việc đạt DoD.

**Product Backlog refinement là hoạt động liên tục**, không phải event Scrum bắt buộc với lịch/timebox cố định. Không nên chờ Sprint Planning mới phát hiện cần truy cập sandbox đối tác chưa được cấp.

### 11.2. Sprint Planning: ba chủ đề

Scrum Planning trả lời:

1. **Why is this Sprint valuable?** Product Owner đề xuất cách sản phẩm tăng giá trị; cả Scrum Team xác định Sprint Goal.
2. **What can be Done this Sprint?** Developers cùng Product Owner làm rõ Product Backlog Items, Developers lựa chọn lượng công việc có thể hoàn tất trong Sprint.
3. **How will the chosen work get Done?** Developers lập kế hoạch đủ để bắt đầu và thích ứng khi làm việc.

Ví dụ:

**Product Goal:** tự phục vụ ghi danh và vào bài đầu đúng quyền.

**Sprint Goal:** “Ghi danh khóa miễn phí end-to-end đạt DoD cho người học đủ điều kiện.”

**PBI có thể được lựa chọn theo bối cảnh:**

| PBI | Hành vi người dùng | Rủi ro/điều kiện |
|---|---|---|
| ENR-01 | Ghi danh khóa miễn phí hợp lệ | Kiểm tra trùng ghi danh và dữ liệu bền vững |
| ENR-02 | Sau ghi danh, học viên nhận đúng entitlement | Không cấp quyền trái quy tắc |
| ENR-03 | Từ trang xác nhận, học viên vào bài đầu | Đường dẫn, quyền và accessibility |
| ENR-04 | Người học nhận thông báo rõ nếu không đủ điều kiện | Không báo thành công giả, có hướng hỗ trợ |

Những PBI này là **đề xuất phân rã**, không bảo đảm mọi team đều có thể hoàn tất cả bốn trong hai tuần. Developers cần xét năng lực, kinh nghiệm, loại công việc và DoD trước khi lựa chọn.

### 11.3. Ví dụ Sprint Backlog hướng mục tiêu

~~~text
SPRINT GOAL:
  Hoc vien du dieu kien ghi danh khoa mien phi va vao bai dau.

SELECTED PBIs:
  ENR-01: Ghi danh hop le va luu ban ghi ben vung
  ENR-02: Cap entitlement dung quy tac
  ENR-03: Truy cap bai dau tu trang xac nhan

PLAN (Developers duy tri va dieu chinh):
  - Lam ro acceptance examples + rui ro authz
  - Thiet ke API/data contract
  - Test-first cho luat ghi danh va cap quyen
  - Tich hop UI/API/DB theo lat cat nho
  - Chay CI/integration/authorization tests
  - Kiem tra DoD va review tren Increment

RISKS:
  - Data migration can kiem chung
  - Test environment phai co user roles phu hop
  - Them thong tin tu nguoi hoc co the doi UX
~~~

Sprint Backlog là **kế hoạch cho và bởi Developers**. Nó được điều chỉnh khi học thêm; không nên tự coi mọi task liệt kê ngày đầu là hợp đồng cá nhân bất di bất dịch.

### 11.4. Ngày đầu Sprint: làm một lát cắt nhỏ có evidence

Đội có thể bắt đầu bằng một đường cơ sở tối thiểu:

~~~text
User -> Course enrollment request
     -> Validation -> Persist enrollment
     -> Correct entitlement
     -> Access first lesson
~~~

Với quyền truy cập, ngay phiên bản đầu cần kiểm tra:

- Người đủ điều kiện ghi danh thành công.
- Người không đủ điều kiện không nhận entitlement.
- Người dùng khác không truy cập trái quyền.
- Gửi lại yêu cầu không tạo bản ghi/quyền sai nếu chính sách yêu cầu idempotency.
- Giao diện thông báo trạng thái đúng.

Một prototype có nút hoạt động nhưng truy cập dữ liệu không đúng **không thể được gọi là Increment đạt DoD**.

### 11.5. Daily Scrum: kiểm tra tiến triển tới Sprint Goal

Daily Scrum mẫu:

> “Để đạt luồng ghi danh vào bài, chúng ta còn phụ thuộc entitlement API. Test contract đang fail vì trường trạng thái khác dự kiến. Hôm nay hai Developers cùng xử lý, không kéo thêm ticket UI mới; nếu contract không giải quyết được, Product Owner cần xem lại phạm vi lựa chọn.”

Đây là thông tin giúp điều chỉnh Sprint Backlog.

Ngược lại:

> “A hôm qua làm 8 giờ, B làm 7 giờ, C hôm nay code tiếp.”

...không đủ cho biết có tiến triển tới Sprint Goal hay cần hành động.

Daily Scrum 15 phút không cần giải quyết mọi chi tiết ở ngay đó; các Developers có thể tiếp tục trao đổi kỹ thuật sau Daily khi người liên quan sẵn sàng.

### 11.6. Giữa Sprint: học thêm và thương lượng phạm vi

Giả sử người học thử nghiệm nói trạng thái sau ghi danh khó hiểu. Đội:

1. Xác nhận vấn đề trong phạm vi Sprint Goal.
2. Product Owner làm rõ giá trị và thứ tự.
3. Developers đề xuất giải pháp tối thiểu, kiểm tra accessibility và các trường hợp lỗi.
4. Nếu cần, thương lượng lại phạm vi PBI với Product Owner.
5. Giữ DoD; không “để test qua Sprint sau” nếu PBI sẽ được gọi Done.

Điều này thể hiện **mục tiêu ổn định tương đối, chi tiết thích ứng**, khác giữ mọi task cố định bất kể điều kiện mới.

### 11.7. Trước Sprint Review: minh bạch Increment thực

Đội nên kiểm tra:

- Các PBI nào đã đạt DoD và thực sự thuộc Increment.
- Hành trình nào có thể được sử dụng theo điều kiện áp dụng.
- Những mục nào chưa Done và vì sao.
- Còn rủi ro nào ảnh hưởng người dùng hoặc vận hành.
- Dữ liệu/feedback nào có thể đem tới thảo luận với stakeholders.

Không “chữa cháy demo” bằng dữ liệu giả tạo cảm giác mọi thứ đã xong. Nếu cần một bản trình diễn môi trường an toàn, nói rõ **phạm vi và sự khác biệt** với trải nghiệm người dùng thật.

### 11.8. Sprint Review: kiểm tra giá trị và lựa chọn tiếp

Mẫu câu hỏi tương tác:

1. “Có thể thao tác ghi danh và vào bài đầu trên Increment đã đạt DoD không?”
2. “Học viên nào đủ điều kiện, tình huống nào chưa hỗ trợ?”
3. “Những tín hiệu nào khác dự đoán của chúng ta?”
4. “Điều gì từ vận hành/kinh doanh thay đổi thứ tự Product Backlog?”
5. “Lát cắt nào nên làm tiếp để hướng tới Product Goal?”

Review không chỉ là đội “bảo vệ” kết quả trước lãnh đạo. Product Owner, Developers và stakeholders cùng **học về sản phẩm**; Product Backlog có thể được điều chỉnh.

### 11.9. Sprint Retrospective: cải tiến dòng làm việc

Giả sử Sprint Goal đạt nhưng integration test phát hiện mismatch muộn. Retrospective:

~~~text
OBSERVED:
  2 PBIs bi cho do API contract chua thong nhat.
  Test integration phat hien loi muon.

HYPOTHESIS:
  Neu lam ro contract va vi du loi som,
  thi bot item bi blocked o Verification.

EXPERIMENT:
  Sprint tiep theo, voi PBI authz:
  - Thao luan vi du voi PO/Developers/test specialist.
  - Chay contract checks trong CI.
  - Xem work item age va so mismatch phat hien muon.

GUARDRAIL:
  Khong ha DoD, khong bo test phan quyen.

REVIEW:
  Danh gia sau hai Sprint theo cung metric definition.
~~~

**Retrospective có tác dụng khi hành động được thử và kiểm tra lại**, không khi chỉ tạo danh sách 20 lời khuyên không có owner.

### 11.10. Từng ngày trong Sprint là hướng tới mục tiêu, không phải mini-waterfall

<table>
<tr><th>Mốc trong Sprint hai tuần minh họa</th><th>Điều cần tập trung</th><th>Điều không nên hiểu sai</th></tr>
<tr><td>Ngày 1</td><td>Planning, xác định Sprint Goal và kế hoạch đủ để bắt đầu</td><td>Chốt vĩnh viễn mọi task/cách viết code</td></tr>
<tr><td>Ngày 2–3</td><td>Tích hợp lát cắt sớm, test hành vi quan trọng</td><td>UI làm hết trước, API làm tuần sau</td></tr>
<tr><td>Ngày 4–5</td><td>Kiểm tra Increment đầu tiên và rủi ro phụ thuộc</td><td>Đợi hết Sprint mới nhìn build chung</td></tr>
<tr><td>Ngày 6–8</td><td>Làm rõ/điều chỉnh phạm vi theo feedback và Sprint Goal</td><td>Nhận mọi yêu cầu mới bất kể mục tiêu</td></tr>
<tr><td>Ngày 9</td><td>Xác nhận DoD, chuẩn bị bằng chứng tương tác phù hợp</td><td>Chạy QA lần đầu khi không còn thời gian sửa</td></tr>
<tr><td>Ngày 10</td><td>Review kết quả sản phẩm, retrospective về cách làm</td><td>Hai buổi báo cáo tỷ lệ hoàn thành cho cấp quản lý</td></tr>
</table>

**Đây không phải một lịch ngày chính thức trong Scrum Guide.** Team có thể tích hợp và tạo nhiều Increment vào bất kỳ ngày nào; điều quan trọng là vừa tạo giá trị vừa nhận feedback trong nhịp Sprint.

## 12. Tình huống xuyên suốt: chọn Scrum cho năng lực ghi danh, Kanban cho hỗ trợ vận hành

> **Toàn bộ tên đội, số liệu và diễn biến trong phần này là ví dụ giả định**, không phải thông tin vận hành của doanh nghiệp cụ thể hoặc phép đo chuẩn cho mọi tổ chức.

Nền tảng học trực tuyến có hai dòng công việc:

**Dòng A — Phát triển sản phẩm ghi danh:** nhóm gồm Product Owner, Developers và Scrum Master; cần cải thiện khả năng học viên chọn khóa, thanh toán hợp lệ và vào bài đầu. Có roadmap định hướng nhưng giải pháp/cách ưu tiên cần học từ người dùng và tích hợp.

**Dòng B — Vận hành hỗ trợ nền tảng:** nhóm phục vụ hệ thống deploy, monitoring, on-call và yêu cầu môi trường liên tục. Công việc có nhiều item khẩn, thời hạn theo mức ảnh hưởng và policy dịch vụ.

Lãnh đạo ban đầu yêu cầu **cả hai nhóm làm Sprint hai tuần** để thống nhất dashboard. Sau chẩn đoán, nhóm phát hiện hai dòng cần **cơ chế quản lý khác nhau**.

### 12.1. Dữ liệu hiện trạng để lựa chọn, không chấm điểm người

| Tín hiệu giả định | Dòng A — sản phẩm ghi danh | Dòng B — vận hành nền tảng |
|---|---|---|
| Mục tiêu công việc | Một Product Goal khá rõ | Giữ reliability và đáp ứng nhiều service requests |
| Khả năng lựa chọn phạm vi | PO có thể ưu tiên PBI theo giá trị/rủi ro | Phần lớn việc đến theo sự cố hoặc yêu cầu hỗ trợ |
| Increment ngắn hạn | Có thể chia một số hành vi UI/API/DB/test | Có thay đổi nhỏ dùng được, nhưng không luôn tạo một mục tiêu ngắn hạn thống nhất |
| Tính bất định | Nhu cầu/thiết kế sản phẩm cần feedback thường xuyên | Tải công việc và độ khẩn thay đổi hằng ngày |
| Stakeholder review | Học viên, hỗ trợ, chủ khóa có thể review tác vụ | Service consumers cần SLE, reliability, thời gian đáp ứng |
| Điểm nghẽn | DoD/tích hợp, ưu tiên và trải nghiệm người dùng | WIP, on-call, môi trường và ticket queue |

Kết luận sơ bộ: **Scrum đáng thử cho dòng A** nếu xây được năng lực tạo Increment đạt DoD; **Kanban đáng thử cho dòng B** với policies rõ, flow metrics và service review. Đây là lựa chọn theo nhu cầu, **không phải đánh giá nhóm nào “Agile hơn”**.

### 12.2. Một Product Goal cho dòng A

> “Học viên đủ điều kiện có thể ghi danh các khóa được hỗ trợ, nhận đúng quyền và vào bài đầu với trạng thái rõ ràng mà không cần sự can thiệp thủ công trong trường hợp chuẩn.”

Kết quả cần kiểm chứng:

- Luồng ghi danh nào đã đạt DoD?
- Học viên thuộc cohort nào thực sự vào bài đầu?
- Có lỗi trạng thái thanh toán, cấp quyền hoặc dữ liệu không?
- Những tác vụ nào học viên không hiểu dù chức năng kỹ thuật đã Done?

Không tự lấy **tăng số PBI Done** làm bằng chứng cuối rằng Product Goal đã hoàn thành.

### 12.3. Vì sao dòng A chọn Scrum

1. Có một sản phẩm với người dùng và vấn đề chung.
2. Có nhu cầu chọn **một kết quả ngắn hạn có ý nghĩa** thay vì hàng loạt task nhỏ.
3. Có thể tạo Increment đầu-cuối nếu cải thiện integration/DoD.
4. Stakeholders có thể nhận phản hồi qua Sprint Reviews.
5. Product Owner có thể điều chỉnh Product Backlog theo bằng chứng.
6. Đội có thể dùng Retrospective để giảm điểm nghẽn kỹ thuật/phối hợp.

**Điều kiện còn phải cải thiện:** contract entitlement và môi trường integration còn yếu. Chọn Scrum không xóa rủi ro; đội đưa năng lực test/CI thành phần việc hỗ trợ tạo Increment.

### 12.4. Vì sao dòng B không ép vào Sprint Goal giả

Dòng B nhận sự cố production, khắc phục build runner, nâng cấp secret rotation và hỗ trợ môi trường. Một Sprint Goal cố định như “đóng 25 ticket” không gắn một kết quả sản phẩm chung và dễ mất ý nghĩa khi sự cố nghiêm trọng xảy ra.

Nhóm B có thể định nghĩa:

~~~text
SERVICE GOAL:
  Ho tro cac product teams trien khai an toan,
  giam thoi gian cho ha tang va phuc hoi su co phu hop.

WORKFLOW:
  Requested -> Ready -> In Progress -> Verification -> Done

POLICIES:
  WIP control theo nang luc thuc.
  Expedite xu ly su co theo severity va owner.
  Blocked hien ro; khong loai khoi WIP trong boundary.
  Done phai dap ung tieu chuan dich vu va bao mat.

FEEDBACK:
  Service review va incident learning.
  Dinh ky xem SLE/age, lead time, reliability va outcome.
~~~

Nhóm B vẫn có **mục tiêu dài hạn, review định kỳ, chất lượng kỹ thuật và phương pháp học**. Chỉ khác là họ không buộc mọi việc vào một cam kết Sprint Goal không phù hợp với tính chất công việc.

### 12.5. Phối hợp hai dòng mà không làm mất quyền ưu tiên

Sản phẩm ghi danh cần môi trường test mới từ nhóm platform. Hai nhóm nên làm rõ:

- Người tiêu thụ dịch vụ cần năng lực gì và khi nào?
- Có thể dùng self-service API/template hay phải mở ticket?
- Điều kiện an toàn và quyền truy cập ra sao?
- Ai quyết định ưu tiên nếu platform phải xử lý incident khẩn?
- Product Team có phương án giảm phụ thuộc hoặc mock với contract được kiểm chứng ở mức nào?

Không nên giao cho Product Owner của sản phẩm ghi danh quyền đổi backlog dịch vụ platform nếu platform phục vụ nhiều sản phẩm độc lập. Họ cần **hợp đồng, đường trao đổi và ưu tiên xuyên sản phẩm** theo trách nhiệm tổ chức.

### 12.6. Sprint đầu của dòng A

**Sprint Goal đề xuất:** “Học viên ghi danh miễn phí và vào bài đầu end-to-end đạt DoD.”

Product Owner và Developers chọn một số PBI sau refinement. Trong Sprint:

- API và UI được tích hợp liên tục theo lát cắt.
- Các điều kiện quyền và dữ liệu được test sớm.
- Work item age hiện ra nếu PBI bị chặn ở hợp đồng với nền tảng.
- Nhóm dùng Sprint Review kiểm tra Increment thật và học từ người học.
- Retrospective chọn một cải tiến integration contract.

Nếu sau Sprint một số PBI chưa Done, đội giữ trạng thái trung thực và không cộng chúng vào Increment. Sprint Goal có thể đạt hoặc chưa đạt theo điều thực tế, không được đổi tiêu chí cuối Sprint để làm đẹp báo cáo.

### 12.7. Tín hiệu sau vài Sprint

Ví dụ dữ liệu giả định của dòng A:

| Tín hiệu | Giai đoạn trước | Giai đoạn thử Scrum | Điều kiện đọc |
|---|---:|---:|---|
| PBI đạt DoD trong các chu kỳ tương đương | 12 | 15 | Cùng loại PBI, DoD, thời kỳ và work mix? |
| Median cycle time của PBI Done | 9 ngày | 7 ngày | Có item đang mở già tuổi không? |
| Các hạng mục bị blocked cuối kỳ | 6 | 3 | Blocked có được ghi nhận nhất quán? |
| Tỷ lệ học viên đủ điều kiện vào bài đầu | 80% | 84% | Cùng cohort/mẫu số/cửa sổ/event tracking? |
| Lỗi cấp quyền nghiêm trọng trong phạm vi theo dõi | 2 | 0 | Dữ liệu/số lượng người dùng và cơ chế phát hiện? |

**Không được kết luận** “Scrum làm năng suất tăng chính xác 25%” chỉ từ số PBI hoặc “Scrum làm outcome tăng 4 điểm phần trăm” khi còn nhiều thay đổi đồng thời. Có thể nói **có những tín hiệu đáng tiếp tục kiểm tra**, kèm giả định/giới hạn và quyết định thử tiếp.

### 12.8. Tín hiệu từ dòng B

Kanban cũng không được đánh giá chỉ bằng số ticket Done. Dòng B xem:

- Work item age của yêu cầu đang chờ.
- WIP theo class of service.
- Throughput của cùng loại request.
- Cycle time tới trạng thái Done theo chuẩn dịch vụ.
- SLE với thời gian và xác suất.
- Reliability/deployment incidents và thời gian khôi phục theo nguồn dữ liệu phù hợp.
- Thời gian các Product Teams phải chờ để có môi trường/công cụ dùng được.

Nếu platform “đóng” yêu cầu nhanh bằng cách chuyển trạng thái sang Resolved trước khi service consumer dùng được, dashboard đẹp hơn nhưng **dịch vụ kém đi**. Cũng như Scrum, Kanban cần **định nghĩa Done và giá trị rõ**.

### 12.9. Khi nào hai dòng có thể điều chỉnh lại cách làm?

Nếu dòng B giảm sự cố và bắt đầu xây một platform capability lớn với Product Goal rõ, họ có thể cân nhắc tổ chức một nhóm dùng Scrum cho phần phát triển năng lực. Nếu dòng A chuyển sang phần lớn công việc bảo trì/incidents bất ngờ, họ phải xem lại khả năng giữ Sprint Goal và quản lý dòng việc.

**Chọn cách tiếp cận là quyết định cần được xem lại theo dữ liệu**, không phải nhãn vĩnh viễn của một phòng ban.

## 13. Pilot Scrum có mục tiêu: kiểm tra giả thuyết trước khi triển khai rộng

Chọn Scrum cho một tổ chức không cần bắt đầu bằng “đổi 20 teams sang Sprint cùng lúc”. Nếu có một dòng sản phẩm với ranh giới đủ rõ, có thể **thử trong phạm vi hạn chế**, duy trì sự thật về chất lượng và dữ liệu rồi đánh giá.

### 13.1. Trước pilot cần đặt một giả thuyết

Ví dụ:

> “Nếu nhóm ghi danh dùng Product Goal và Sprint Goal để tập trung vào lát cắt đầu-cuối, đồng thời có Sprint Review với stakeholders và CI/DoD rõ, thì họ sẽ phát hiện giả định sai sớm hơn và tạo Increment có thể sử dụng thường xuyên hơn, mà không tăng rủi ro cấp quyền.”

Giả thuyết này có:

- **Vấn đề:** công việc phân tán, tích hợp và phản hồi muộn.
- **Cơ chế thay đổi:** mục tiêu tập trung, nhịp inspection, chất lượng tích hợp.
- **Kết quả kỳ vọng:** phản hồi sớm hơn và Increment dùng được.
- **Guardrail:** không làm xấu bảo mật, quyền và tính đúng đắn dữ liệu.

Không nên viết:

> “Nếu đội dùng Scrum, velocity sẽ tăng 30%.”

Velocity là đơn vị ước lượng tương đối nội bộ, không chứng minh năng suất hay outcome, lại dễ bị thao túng khi gắn KPI.

### 13.2. Chọn phạm vi pilot

Một phạm vi có ích thường có:

1. **Product boundary rõ**, không cần cả công ty thống nhất cấu trúc ngay.
2. Product Owner có khả năng quản lý Product Backlog trong phạm vi.
3. Scrum Team có năng lực đủ để tạo Increment hoặc có kế hoạch cải thiện năng lực trong pilot.
4. Stakeholders/người dùng có thể cho phản hồi thực.
5. Rủi ro và phụ thuộc đủ thấy để quản lý có kiểm soát.
6. Không dùng người dùng thực làm đối tượng thử nghiệm an toàn chưa được bảo vệ.

Nếu pilot chỉ chọn một đội nổi bật, có chuyên gia toàn thời gian và không phụ thuộc gì, kết quả có thể **khó nhân rộng** cho tổ chức khác. Nên ghi các điều kiện đặc biệt từ đầu.

### 13.3. Chuẩn bị Product Backlog và DoD trước Sprint đầu

Không cần refinement chi tiết toàn bộ sản phẩm. Cần đủ để:

- Product Goal hướng dẫn lựa chọn.
- Có PBI đầu tiên theo lát cắt có giá trị.
- Các trường hợp lỗi/biên quan trọng được làm rõ.
- DoD và điều kiện tích hợp đủ tin để gọi Increment Done.
- Những phụ thuộc sớm như sandbox, test data và quyền được biết.

**Không bắt đầu Sprint khi mọi thông tin hoàn hảo**; Scrum cho phép học khi làm. Nhưng cũng không cố khởi động khi không có Product Goal, không có quyền ưu tiên và không thể định nghĩa Done, rồi kỳ vọng Sprint Review tự sửa tất cả.

### 13.4. Cửa sổ thử và thời điểm đánh giá

Một mẫu có thể là **ba đến sáu Sprint**, tùy độ dài Sprint, loại công việc và nhịp phản hồi. Đây **không phải quy định Scrum**; chỉ là gợi ý để tránh kết luận từ một Sprint bất thường.

Đánh giá:

- **Sau mỗi Sprint:** đã tạo Increment nào, Review học gì, Retro chọn gì, Sprint Goal có còn phù hợp?
- **Sau vài Sprint:** các cơ chế có cải thiện việc tập trung và thời gian phản hồi không?
- **Sau giai đoạn thử:** giữ/điều chỉnh cách làm hay dùng cách khác cho dòng việc này?

Không cam kết một tỷ lệ cải thiện trước khi dữ liệu có cơ sở.

### 13.5. Năm điều kiện không nên thỏa hiệp khi pilot

| Điều kiện | Vì sao quan trọng | Dấu hiệu đã vi phạm |
|---|---|---|
| **Product Owner thực quyền** | Một thứ tự Product Backlog có nghĩa | Mỗi quản lý đưa task riêng trực tiếp vào Sprint |
| **Sprint Goal tập trung** | Đội biết điều cần bảo vệ và điều có thể thương lượng | Sprint Goal là “đóng N ticket” |
| **DoD và Increment có thể sử dụng** | Inspection dựa trên sự thật sản phẩm | Code Complete được báo Done, test chuyển sang Sprint sau |
| **Scrum events tạo inspection/adaptation** | Có vòng học định kỳ | Review chỉ đọc slide, Retro không thử cải tiến |
| **Dữ liệu và guardrails trung thực** | Không tối ưu số liệu bằng cách gây rủi ro | Che blocked items, không báo lỗi phân quyền |

Nếu những điều kiện này không tồn tại trong pilot, nên **báo khoảng trống điều kiện triển khai** thay vì tuyên bố “Scrum đã được thử nhưng không hiệu quả”.

### 13.6. Một bảng kế hoạch pilot minh họa

| Giai đoạn | Điều cần làm | Bằng chứng hoàn thành |
|---|---|---|
| **Chuẩn bị** | Xác định Product Goal, PO, DoD, PBI nhỏ, baseline flow | Product boundary và quyết định được ghi rõ |
| **Sprint 1** | Tạo Increment đầu tiên có thể dùng trong phạm vi | Có bằng chứng DoD và Review học được gì |
| **Sprint 2** | Tập trung cải thiện điểm chặn của Sprint 1 | Mismatch/blocked được xử lý sớm hơn nếu dữ liệu hỗ trợ |
| **Sprint 3** | Phản hồi sản phẩm dẫn đến điều chỉnh backlog | Một quyết định giá trị có căn cứ |
| **Sprint 4+ nếu cần** | Quan sát tính bền vững, nợ kỹ thuật và workload | Dữ liệu nhiều kỳ và rủi ro còn mở |
| **Đánh giá** | Chọn giữ, thay đổi điều kiện hoặc chuyển cách tiếp cận | Báo cáo có giới hạn, owner và bước tiếp |

Không phải Sprint 1 nhất thiết phải thành công với mọi PBI đã chọn. Quan trọng là **đừng che sự thật, giữ chất lượng và học rõ nguyên nhân**.

### 13.7. Những thay đổi đồng thời có thể làm sai kết luận

Trong pilot, tổ chức có thể:

- Đổi quy mô đội, thêm một chuyên gia.
- Thay CI/test environment.
- Chuyển từ tích hợp thanh toán khó sang bug UI dễ.
- Thay cách chia PBI.
- Nâng Definition of Done.
- Sửa cơ chế analytics.
- Có chiến dịch marketing làm thay cơ cấu người học.

Nếu cycle time hoặc outcome đổi, **không thể tự quy toàn bộ cho Scrum**. Cần ghi những điều thay đổi và phân tích cùng work type, DoD, ranh giới workflow/cohort khi có thể.

### 13.8. Khi pilot không cải thiện nên làm gì?

Một pilot có thể không tạo tín hiệu tốt. Đừng mặc định:

- “Nhân viên chưa Agile nên phải học Scrum tiếp.”
- “Scrum không bao giờ phù hợp.”
- “Chỉ cần kéo Sprint dài hơn sẽ giải quyết.”

Thay vào đó, phân biệt:

1. **Scrum bị thiếu điều kiện?** PO không có quyền, không có DoD, không tạo Increment.
2. **Áp dụng chưa đúng?** Review không inspection, Daily thành status report.
3. **Cách làm đúng nhưng không giải quyết vấn đề chính?** Dịch vụ cần flow continuous, không cần Sprint Goal.
4. **Kỹ thuật và phụ thuộc đang giới hạn?** CI, code coupling, môi trường hoặc đối tác.
5. **Dữ liệu đánh giá sai?** Đơn vị item, cửa sổ, chất lượng, work mix đổi.

Kết luận cuối phải phù hợp **nguyên nhân quan sát được**, không bảo vệ framework vì uy tín hoặc loại bỏ framework vì một Sprint khó khăn.

## 14. Đo Scrum theo cơ chế giá trị, không theo sự tuân thủ nghi thức

Một đội có thể tổ chức đủ mọi event và vẫn không tạo Increment dùng được. Vì vậy **độ đầy đủ lịch họp không phải thước đo cuối của Scrum**.

### 14.1. Bốn nhóm bằng chứng

| Nhóm bằng chứng | Câu hỏi | Ví dụ tín hiệu | Giới hạn |
|---|---|---|---|
| **Mục tiêu và lựa chọn sản phẩm** | Sprint Goal giúp tập trung vào giá trị không? | PBI được chọn phục vụ mục tiêu, Product Backlog đổi theo feedback | “Tỷ lệ đạt Sprint Goal” có thể bị gaming nếu đặt goals quá dễ |
| **Increment và chất lượng** | Có phần mềm có thể sử dụng đạt DoD không? | Increment tích hợp, contract tests, sự cố, reliability | Số test hoặc build pass không tự chứng minh giá trị |
| **Flow và khả năng hoàn tất** | Công việc tới Done thế nào? | WIP, throughput, work item age, cycle time, SLE khi dùng | Work types và Done phải cùng định nghĩa |
| **Outcome và học từ người dùng** | Người dùng có đạt kết quả hơn không? | Ghi danh hợp lệ, vào bài đầu, phản hồi hỗ trợ | Cohort, mẫu số, mùa vụ và yếu tố khác có thể ảnh hưởng |

Không nên quy bốn nhóm thành một **“Scrum score = 87/100”** rồi dùng thưởng phạt. Một lỗi cấp quyền nghiêm trọng không thể được “bù” bằng velocity tăng.

### 14.2. Tỷ lệ hoàn thành Sprint Goal không phải bảng KPI cho quản lý

Đội có thể ghi Sprint Goals đạt/chưa đạt để **học cách lựa chọn mục tiêu**. Nhưng nếu tổ chức đặt KPI “mọi Sprint phải đạt 100% Sprint Goal”, nhóm sẽ có động lực:

- Đặt mục tiêu mơ hồ hoặc quá dễ.
- Hạ DoD cuối Sprint.
- Che blocker/rủi ro.
- Tránh thử nghiệm sản phẩm có giá trị nhưng bất định.
- Viết lại mục tiêu cuối Sprint để “khớp số”.

Tốt hơn là kiểm tra **mục tiêu có ý nghĩa, Increment có thật và đội học được gì**, đồng thời xem xu hướng qua nhiều Sprint.

### 14.3. Velocity hỗ trợ dự báo nội bộ, không so năng suất giữa đội

Giả sử:

- Scrum Team A đạt 45 story points/Sprint.
- Scrum Team B đạt 25 story points/Sprint.

Story points là ước lượng tương đối do đội hiệu chỉnh; không có thang chuẩn chung để kết luận A “năng suất hơn 80%”. Ngay trong một đội, thay thang ước lượng hoặc chia PBI có thể làm velocity đổi mà chất lượng/giá trị không đổi.

Nếu dùng velocity, hãy dùng trong phạm vi **dự báo lượng công việc của cùng đội theo lịch sử đủ ổn định**, không thưởng/phạt hoặc dùng để so trình độ cá nhân.

### 14.4. Bốn Kanban flow metrics làm sáng tỏ tiến triển

Trong một Scrum Team có Definition of Workflow được xác định:

| Metric | Định nghĩa cơ bản | Câu hỏi Retrospective |
|---|---|---|
| **Work in Progress (WIP)** | Số item đã Started nhưng chưa Finished trong workflow | Đội có mở quá nhiều việc cùng lúc không? |
| **Throughput** | Số item Finished trong một khoảng thời gian | Những item Done có cùng đơn vị/DoD không? |
| **Work Item Age** | Thời gian item đang mở đã ở workflow | Item nào bị blocked già tuổi và cần giúp hoàn tất? |
| **Cycle Time** | Elapsed time từ Started tới Finished của item đã hoàn tất | Các bước chờ nào làm thời gian tăng? |

Với **SLE** (Service Level Expectation), nên nêu thời lượng và xác suất từ dữ liệu/giả định phù hợp, ví dụ “85% PBI loại X được hoàn tất trong 12 ngày lịch” nếu có cơ sở. SLE không biến mọi PBI thành một lời hứa chắc chắn.

### 14.5. Ví dụ work item age tránh ngụy kết luận từ Done

Sprint này có năm PBI Done với cycle time **2, 3, 4, 5, 6 ngày**, trung vị bằng 4 ngày. Đồng thời còn ba PBI chưa Done với work item age **12, 17 và 22 ngày**.

Không được viết:

> “Mọi việc nay chỉ mất bốn ngày, Scrum đã giải quyết điểm nghẽn.”

Kết luận có căn cứ hơn:

> “Median cycle time của năm PBI Done là bốn ngày. Ba PBI còn mở đã có age 12, 17 và 22 ngày; cần điều tra dependency/blocker và điều kiện DoD. Dữ liệu một Sprint chưa đủ kết luận xu hướng.”

Chỉ xem item Done dễ tạo **survivorship bias** và che hạng mục khó.

### 14.6. Metric contract giúp dữ liệu đáng tin

Ví dụ \`CycleTime.PBI.v1\`:

~~~text
METRIC:
  Cycle Time of Product Backlog Items

POPULATION:
  PBI/bug duoc dinh nghia trong workflow, khong dem subtask.

START:
  Lan dau item duoc keo vao In Progress.

DONE:
  Item thuc su dat DoD cua san pham trong pha quan sat.

WINDOW:
  Calendar days; timezone va data cutoff da cong bo.

REOPEN:
  Dinh nghia chinh sach rework va Done cuoi.

EXCLUSIONS:
  Canceled / duplicate theo quy tac nhat quan.

CHECK:
  Missing, negative timestamps, repeated Done events.

CONTEXT:
  Work type, granularity, workflow version, do phuc tap phu thuoc.
~~~

Một dashboard trước–sau có thể không so được nếu tuần đầu Done nghĩa “code merged”, tuần sau Done nghĩa “đạt DoD”. **Không nối các số có cùng nhãn nhưng khác ý nghĩa** để tuyên bố Scrum tốt hơn.

### 14.7. Chất lượng và outcome là guardrails

Khi chọn Scrum, không nên chỉ hỏi:

> “Bao nhiêu PBI Done sau mỗi Sprint?”

Cần hỏi thêm:

- PBI đó đạt Definition of Done chưa?
- Sự cố sau release có tăng không, mức độ nào?
- Người dùng có thể hoàn tất tác vụ đúng quyền không?
- Có test quan trọng nào bị tắt để pipeline xanh không?
- Nhóm có thể duy trì thay đổi thường xuyên mà không kiệt sức không?
- Người dùng bị lỗi có được tính vào dữ liệu không?

Một số ví dụ:

| Tín hiệu nhìn tốt | Câu hỏi còn thiếu |
|---|---|
| Throughput PBI tăng 20% | Cùng work type, granularity, DoD và quality? |
| CI chạy trong 4 phút thay 10 phút | Có bỏ bước test bảo vệ rủi ro quan trọng? |
| Conversion đăng ký tăng | Cùng cohort, denominator, cửa sổ, phân khúc miễn phí/trả phí? |
| Ít production bugs hơn | Monitoring, traffic và khả năng ghi nhận có thay đổi? |
| Sprint Goals luôn đạt | Có đặt mục tiêu đủ có ý nghĩa hoặc hạ định nghĩa đạt? |

### 14.8. Không chứng minh quan hệ nhân quả chỉ từ trước–sau

Nếu sau pilot Scrum đội có cycle time thấp hơn, cần xem:

- CI đã được nâng cấp cùng kỳ chưa?
- Số Developers hoặc seniority có đổi?
- Work mix chuyển từ feature tích hợp sang bug nhỏ?
- Product Owner có thêm quyền?
- PBI được chia dọc tốt hơn?
- Đối tác bên ngoài đã hết lỗi?

Có thể kết luận “sau nhiều thay đổi trong pilot, flow có tín hiệu cải thiện trong phạm vi đo”; **chưa thể quy toàn bộ cho Scrum** nếu chưa có bằng chứng loại bớt lời giải thích thay thế.

### 14.9. Review phản hồi tốt hơn chỉ một biểu đồ

Trong Sprint Review, một học viên thử:

1. Chọn khóa.
2. Ghi danh hợp lệ.
3. Nhận quyền đúng.
4. Vào bài đầu.

Phản hồi này có giá trị khác với dashboard “13 story points Done”. Kết hợp **quan sát hành vi và dữ liệu định lượng** giúp Product Owner lựa chọn tiếp theo. Nhưng một buổi thử với hai người không tự chứng minh tỷ lệ thành công của toàn dân số; cần biết giới hạn mẫu.

## 15. Các quyết định khó khi sử dụng Scrum trong tổ chức thực

Lý do chọn Scrum cần được thử qua những tình huống gây áp lực. Dưới đây là cách phân biệt **điều phải bảo vệ, điều có thể thương lượng và điều cần thay đổi ở tổ chức**.

### 15.1. Stakeholder đưa yêu cầu mới giữa Sprint

**Tình huống:** Marketing muốn banner ưu đãi ngay, trong khi Sprint Goal đang tập trung sửa luồng quyền học.

**Không nên:** Product Owner nhận mọi yêu cầu rồi thêm task vào Sprint Backlog như chỉ tiêu bắt buộc, khiến Developers không còn quyền thích ứng kế hoạch.

**Hướng xử lý:** làm rõ giá trị/độ khẩn, Product Owner quản lý Product Backlog. Nếu yêu cầu không cần xử lý ngay, cân nhắc theo thứ tự tiếp theo. Nếu có lý do thực, Scrum Team trao đổi ảnh hưởng Sprint Goal và phạm vi; **không hạ DoD để nhét thêm việc**.

### 15.2. Sự cố production nghiêm trọng

**Tình huống:** sai phân quyền khiến học viên thấy đơn của người khác; đội đang giữa Sprint.

**Không nên:** từ chối xử lý vì “không có trong Sprint Backlog”, hoặc tự bỏ kiểm soát để kịp deadline.

**Hướng xử lý:** giảm ảnh hưởng theo incident/security process phù hợp, minh bạch tác động Sprint Goal và điều chỉnh kế hoạch trong quyền của Scrum Team. Nếu công việc khẩn chi phối lặp lại, xem lại năng lực, việc phân luồng và cách tiếp cận phù hợp.

### 15.3. Phụ thuộc API chưa sẵn sàng

**Tình huống:** PBI cần payment sandbox mà nhà cung cấp chưa cấp; Sprint Goal yêu cầu giao dịch thật thành công.

**Không nên:** coi mock trả SUCCESS là bằng chứng tích hợp thật hoặc cam kết dựa vào lịch hứa của đối tác không kiểm soát.

**Hướng xử lý:** làm rõ sớm trong refinement, thử contract/spike khi thích hợp, chọn một lát cắt đạt DoD không tuyên bố vượt bằng chứng, thương lượng lại scope với Product Owner. Nếu dependency khiến Sprint Goal không thực tế, đó là vấn đề lựa chọn mục tiêu cần cải thiện.

### 15.4. QA đòi một “Sprint test” riêng

**Tình huống:** Developers viết code ở Sprint A, tester kiểm chứng ở Sprint B, release ở Sprint C.

**Không nên:** gọi các PBI Code Complete ở Sprint A là Increment đạt DoD rồi hứa sẽ kiểm tra sau.

**Hướng xử lý:** thay cách chia và năng lực: tester tham gia sớm, kiểm thử tự động, môi trường, hợp đồng và integration nằm trong công việc hướng DoD. Nếu một sự kiểm định bên ngoài không thể hoàn tất trong Sprint, cần phân biệt **phạm vi Increment có thể dùng** và các điều kiện phát hành thêm, không tuyên bố sai về Done.

### 15.5. Product Owner muốn hứa mọi PBI đã chọn

**Tình huống:** đội chọn bảy PBI trong Planning; trong Sprint phát hiện hai PBI phức tạp hơn dự kiến.

**Không nên:** giữ tất cả bằng cách bỏ tests hoặc tăng làm ngoài giờ kéo dài để đạt “100% cam kết scope”.

**Hướng xử lý:** Developers cập nhật kế hoạch, làm rõ/đàm phán scope với Product Owner, giữ Sprint Goal và DoD. **Commitment chính thức của Sprint Backlog là Sprint Goal**, không phải lời hứa mọi dự đoán ban đầu về khối lượng đều chắc chắn.

### 15.6. Một Sprint Goal quá mơ hồ

**Tình huống:** Sprint Goal = “cải thiện nền tảng”.

**Không nên:** đánh dấu đạt chỉ vì bất kỳ task nào hoàn tất.

**Hướng xử lý:** làm rõ kết quả có thể kiểm chứng, ví dụ “học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu qua Increment đạt DoD”, hoặc một năng lực kỹ thuật rõ liên hệ Product Goal.

### 15.7. Một Sprint Goal quá tham vọng

**Tình huống:** đội muốn đồng thời thay nhà cung cấp thanh toán, thiết kế lại quyền, chuyển database và ra ứng dụng di động mới trong hai tuần.

**Không nên:** coi đây là “tham vọng Agile” và giao kế hoạch giả chắc chắn.

**Hướng xử lý:** chọn một bước giá trị có thể kiểm chứng, chia nhỏ rủi ro theo ưu tiên, thử discovery/spike nếu cần, ghi những giả định chưa được bảo đảm. Một Sprint Goal nên đủ tập trung để Developers phối hợp hướng một mục tiêu có ý nghĩa.

### 15.8. Một Sprint chỉ giao prototype

**Tình huống:** nhóm có mock UI với dữ liệu giả, chưa tích hợp API, chưa đạt DoD.

**Không nên:** gọi mock đó là Increment sản phẩm đạt DoD. Nó có thể là bằng chứng **discovery/thiết kế**, hữu ích để học về nhu cầu, nhưng khác phần mềm sẵn dùng.

**Hướng xử lý:** giữ nhãn bằng chứng trung thực. Nếu Scrum được chọn cho phát triển sản phẩm, cần xây năng lực tạo Increment có thể dùng; nếu công việc hiện tại thuần nghiên cứu, chọn vòng discovery phù hợp thay vì biến mọi thử nghiệm thành “Done”.

### 15.9. Sprint Review chỉ có quản lý và slide

**Tình huống:** các bên xem 30 slides về velocity, không có Increment hoặc cơ hội điều chỉnh Product Backlog.

**Không nên:** đánh giá Review thành công chỉ vì đúng lịch/thời lượng.

**Hướng xử lý:** mang kết quả sản phẩm và phản hồi thực, mời stakeholders phù hợp, thảo luận tiến triển Product Goal và thích ứng. Review không phải trình diễn đóng một chiều.

### 15.10. Daily Scrum biến thành điểm danh

**Tình huống:** mỗi Developer báo từng phút làm gì để quản lý ghi nhận utilization.

**Không nên:** dùng Daily như công cụ kiểm soát cá nhân. Nó không trả lời về tiến triển Sprint Goal hoặc blocker.

**Hướng xử lý:** Developers tự kiểm tra kế hoạch, nêu điều cản Sprint Goal và quyết định phối hợp phù hợp; vấn đề phức tạp trao đổi tiếp sau Daily với đúng người.

### 15.11. Lãnh đạo dùng velocity để so hai Scrum Teams

**Tình huống:** một team có 40 points, team khác 20, quản lý kết luận team đầu làm việc nhanh gấp đôi.

**Không nên:** so points giữa thang ước lượng nội bộ, khác work mix và DoD.

**Hướng xử lý:** dùng lịch sử dự báo trong phạm vi đội khi hữu ích; đánh giá Increment, quality, outcome, flow và hệ thống phụ thuộc, không xếp hạng qua story points.

### 15.12. Đội bắt đầu nhiều PBI để “không ai rảnh”

**Tình huống:** đến giữa Sprint có 14 PBI In Progress, không item nào hoàn tất.

**Không nên:** mở thêm việc để giữ mọi người bận.

**Hướng xử lý:** dùng WIP/age, tập trung giúp các item gần Done, tháo blocker, swarming/pairing khi phù hợp và làm rõ phân phối năng lực. Việc bận rộn cục bộ không tự bằng flow tốt.

### 15.13. Sprint bị đổi ngày cuối vì chưa xong

**Tình huống:** mỗi lần không đạt mục tiêu, quản lý tự kéo dài Sprint thêm một tuần để vẫn báo “đã giao đủ”.

**Không nên:** dùng lịch Sprint co giãn tùy kết quả khi đang tuyên bố Scrum với Sprints độ dài cố định.

**Hướng xử lý:** giữ nhịp Sprint, minh bạch Increment Done và chưa Done, kiểm tra nguyên nhân và điều chỉnh Sprint Planning/Backlog; không làm mờ dữ liệu bằng đổi timebox sau thực tế.

### 15.14. Scrum Master thành người duyệt task

**Tình huống:** mọi Developer phải xin Scrum Master đồng ý trước khi đổi thứ tự công việc kỹ thuật.

**Không nên:** biến accountability hiệu quả Scrum thành quản lý vi mô Sprint Backlog.

**Hướng xử lý:** Developers tự quản kế hoạch trong Sprint; Scrum Master hỗ trợ cải tiến/loại bỏ trở ngại. Product Owner chịu trách nhiệm giá trị/backlog; các giới hạn chất lượng thuộc trách nhiệm chuyên môn và chính sách áp dụng.

### 15.15. Công ty đổi tên Kanban thành Scrum vì hợp đồng

**Tình huống:** đội vận hành vẫn kéo ticket liên tục theo SLA, không có Sprint Goal hoặc Increment product, nhưng báo cáo khách hàng ghi “Scrum Sprints”.

**Không nên:** dùng nhãn sai để tạo cảm giác quy trình trưởng thành hơn.

**Hướng xử lý:** mô tả phương pháp thực và bằng chứng về service flow/quality; nếu khách hàng cần nhịp review, đặt lịch review có mục đích mà không giả định phải thay toàn bộ workflow thành Scrum.

## 16. Những trường hợp ranh giới cần quyết định rõ khi chọn Scrum

Trong một tổ chức có nhiều nhóm và nhiều loại công việc, **chọn Scrum cho một product team** không tự nghĩa toàn tổ chức cần dùng cùng cách vận hành. Những ranh giới dưới đây thường tạo ra nhầm lẫn dẫn đến Scrum hình thức.

### 16.1. Nhiều Scrum Teams cùng một sản phẩm

Khi Scrum Team trở nên quá lớn, Scrum Guide 2020 khuyến nghị cân nhắc tổ chức thành **nhiều Scrum Teams gắn kết cùng product**. Các Scrum Teams cùng sản phẩm cần chia sẻ:

- **Cùng Product Goal.**
- **Cùng Product Backlog.**
- **Cùng Product Owner.**
- **Cùng Definition of Done.**

Các Increment phải tích hợp và có thể sử dụng. Điều này khác mô hình nhóm UI, API và QA mỗi nhóm có một PO, một backlog, một DoD rồi chỉ “ghép kết quả” vào cuối tháng.

Nhưng Scrum Guide **không quy định mọi Scrum Team phải có cùng một Sprint Goal giống hệt nhau**. Mỗi đội có Sprint Goal phù hợp với Sprint Backlog của họ, cùng góp phần vào Product Goal chung và không làm mâu thuẫn Increment.

### 16.2. Scrum of Scrums không thay Product Owner hoặc DoD

Một tổ chức có thể tổ chức Scrum of Scrums hoặc một cuộc đồng bộ liên đội để làm rõ dependencies. Đây **không phải event bắt buộc của Scrum Guide** và không tự giải quyết:

- Hai Product Owners ra thứ tự khác nhau cho cùng product.
- Không ai chịu trách nhiệm API contract.
- CI chưa tích hợp.
- DoD khác nhau, test dồn cuối kỳ.

Một cuộc trao đổi có ích nên nêu **item nào đang cản Increment, ai giúp tháo, quyết định nào cần ngay và điều kiện kiểm chứng**, thay vì chỉ đọc “nhóm A 70%, nhóm B 80%”.

### 16.3. Nhiều sản phẩm độc lập nhưng có phụ thuộc

Ví dụ:

- **Sản phẩm học viên:** tập trung ghi danh và học.
- **Sản phẩm quản lý nội dung:** phục vụ biên tập/xuất bản khóa.
- **Developer Platform:** phục vụ các teams triển khai và giám sát.

Mỗi sản phẩm có thể có người dùng, mục tiêu và quyền ưu tiên riêng. Nếu chúng **thật sự là các products độc lập**, không cần ép mọi thứ vào một Product Backlog khổng lồ chỉ để “Scrum hóa toàn bộ”.

Cần xác định hợp đồng API/data, service levels, quyền release, đổi phiên bản và đường escalation khi phụ thuộc. Nếu platform phục vụ nhiều sản phẩm, Product Owner của sản phẩm học viên không tự có quyền thay mọi thứ tự backlog platform.

### 16.4. Một nhóm làm hai sản phẩm

Một nhóm ít người có thể bị giao cải thiện hai sản phẩm, mỗi sản phẩm có người dùng và yêu cầu riêng. Cần cân nhắc:

- Có đủ năng lực và quyền ưu tiên rõ cho cả hai không?
- Có thể **tập trung vào một Product Goal** trong phạm vi Scrum đã chọn không?
- Nhu cầu hai sản phẩm có thường xuyên tạo xung đột về Sprint Goal không?
- Có thể sắp xếp lại quyền, năng lực hoặc ranh giới nhóm không?

Nếu không có câu trả lời, việc buộc mọi yêu cầu vào một Sprint Goal mơ hồ có thể che xung đột. Giải pháp có thể là làm rõ service boundary/priority hoặc thay cấu trúc trách nhiệm trước khi chọn Scrum.

### 16.5. Hợp đồng ngày giao cố định nhưng phạm vi thay đổi được

Một sản phẩm cần sẵn sàng cho kỳ khai giảng ngày cố định. Scrum có thể hữu ích để **kiểm tra và thích ứng phạm vi** qua các Sprints:

- Product Goal cho kết quả quan trọng.
- Thứ tự PBI theo giá trị/rủi ro.
- Increment có thể sử dụng sau mỗi Sprint.
- Dự báo có bất định và điều kiện chất lượng.
- Quyết định phạm vi ưu tiên khi đến gần ngày giao.

Không nên hứa **ngày cố định + toàn bộ tính năng cố định + chất lượng không đổi + nguồn lực cố định** như thể mọi bất định đều biến mất vì dùng Scrum.

Nếu phạm vi là nghĩa vụ không được giảm, cần **đánh giá khả thi, rủi ro, năng lực và các kiểm soát hợp đồng** rõ ràng; Scrum không làm cam kết phi thực tế trở nên có thật.

### 16.6. Deadline và Sprint timebox là hai loại ràng buộc

**Deadline kinh doanh** là ngày một năng lực phải có mặt theo nghĩa vụ. **Sprint** là chu kỳ tạo Increment và học tập trong Scrum. Một deadline có thể rơi vào giữa Sprint, sau vài Sprint hoặc trước một kiểm định bên ngoài.

Đội không nên mặc định “mỗi Sprint kết thúc là phải release đúng lịch” hoặc “deadline ở cuối quý nên Sprint phải dài ba tháng”. Cần có chiến lược Increment, release và kiểm chứng phù hợp với cả hai loại ràng buộc.

### 16.7. Khi Product Goal chưa đủ rõ

Một số product teams chưa biết vấn đề nào đáng giải; nếu lập tức nhận backlog features theo yêu cầu nội bộ, Sprint Goal có thể chỉ là đo sản lượng.

Hướng cải thiện:

1. Làm rõ người dùng và cơ hội có giá trị.
2. Chọn giả thuyết có rủi ro cao.
3. Tổ chức discovery để có bằng chứng.
4. Định hướng Product Goal đủ rõ cho việc chọn Increment.
5. Nếu dùng Scrum, kết nối discovery với delivery và DoD; không gọi mỗi prototype là Increment.

Không nên xem Product Goal là tài liệu chỉ viết một lần rồi bị bỏ quên. Nó phải giúp đội chọn **điều gì làm trước và vì sao**.

### 16.8. Đội thử Scrum nhưng backlog do bên khác kiểm soát

Một vendor team được khách hàng đưa một danh sách scope cố định và mọi thay đổi cần chờ phê duyệt. Nhóm có thể tổ chức Sprint để giao phần nhỏ, nhưng **accountability Product Owner và quyền quản lý Product Backlog** cần được xác định trong mối quan hệ với khách hàng.

Có thể thương lượng:

- Một Product Owner có quyền thật.
- Các mốc review kết quả và quy trình thay đổi scope.
- Guardrails hợp đồng/chất lượng và trách nhiệm của bên cung cấp.
- Quyền Developers tự quản cách thực hiện.
- Cách cung cấp dữ liệu rủi ro/dự báo theo điều kiện.

Nếu các điều kiện Scrum không thể có, mô tả trung thực quy trình phát triển theo lô và nhịp review vẫn tốt hơn giả định gọi mọi cuộc họp “Sprint” là Scrum.

### 16.9. Khả năng đo giá trị đến chậm hơn nhịp Sprint

Outcome như **tỷ lệ học viên hoàn thành toàn khóa** có thể cần nhiều tuần sau khi đăng ký; một Sprint hai tuần chưa đủ dữ liệu cho kết quả cuối.

Scrum vẫn có thể phù hợp nếu đội:

- Tạo Increment có thể sử dụng mỗi Sprint.
- Xem chỉ số sớm/leading indicators phù hợp và bằng chứng định tính.
- Theo dõi cohort đủ thời gian cho outcome dài hạn.
- Không bịa “conversion đã tăng” chỉ từ demo.

**Nhịp inspection ngắn không đồng nghĩa mọi outcome đều đo được ngay.** Hãy phân biệt bằng chứng về Increment, bằng chứng về hành vi sớm và kết quả dài hạn.

### 16.10. Đổi cách tiếp cận mà không đổ lỗi framework

Sau vài chu kỳ, đội có thể nhận ra:

- Những yêu cầu khẩn chiếm phần lớn thời gian khiến Sprint Goal khó có ý nghĩa.
- Product Goal đã chuyển sang một dịch vụ liên tục.
- Phụ thuộc tổ chức không thể giải quyết trong phạm vi Scrum Team.
- Một workflow kéo việc với service policies mang lại khả năng đáp ứng tốt hơn.

Đội có thể chuyển từ Scrum sang Kanban hoặc kết hợp các thực hành phù hợp, **nhưng giữ những gì đang có tác dụng**: người chịu trách nhiệm giá trị, phản hồi, DoD/quality, kỹ thuật, review và cải tiến. Không cần bôi xấu Scrum để biện minh cho việc đổi hướng.

## 17. Bộ mẫu ra quyết định và triển khai Scrum

Những mẫu sau là **công cụ thực hành gợi ý**, không phải artifacts chính thức bổ sung của Scrum Guide. Nếu chọn Scrum, Product Backlog, Sprint Backlog, Increment cùng commitments vẫn là các artifacts/commitments của framework; các mẫu chỉ giúp đội làm rõ điều kiện và lưu bằng chứng.

### 17.1. Approach Selection Canvas

~~~text
PRODUCT / SERVICE BOUNDARY:
  [Gia tri cho ai, ranh gioi nao?]

VAN DE CAN GIAI QUYET:
  [Mat tap trung? feedback cham? WIP? DoD? incident?]

CONG VIEC CHU YEU:
  [Phat trien san pham / duy tri dich vu / hon hop]

MUC TIEU CAN THEO DUOI:
  [Product Goal / service outcome]

CO HOI INSPECT / ADAPT:
  [Ai xem ket qua, khi nao, quyet dinh gi?]

INCREMENT / DEFINITION OF DONE:
  [Co the tao phan mem dung duoc voi chat luong gi?]

QUYEN QUYET DINH:
  [Product Owner, Developers, service owners, guardrail roles]

PHU THUOC / DUNG LUONG:
  [Nang luc, WIP, voi vendor, QA, platform]

THU NGHIEM PHUONG PHAP:
  [Scrum / Kanban / practices bo sung va vi sao]

TIN HIEU THANH CONG:
  [Goal focus, Increment, quality, flow, outcome]

TIN HIEU CHO THAY KHONG PHU HOP:
  [Goal lien tuc loi thoi, Done ao, doi cho, bat dinh...]

QUYET DINH:
  [Ap dung, sua dieu kien, thu cach khac]

MOC XEM LAI:
  [Sau nhieu chu ky hoac mot su kien co y nghia]
~~~

### 17.2. Product Goal Card

~~~text
SAN PHAM:
  [Nguoi dung / khach hang / stakeholders]

PRODUCT GOAL:
  [Trang thai tuong lai co gia tri]

BAT DINH CAN HOC:
  [Nguoi dung, nghiep vu, ky thuat, dependency]

GUARDRAILS:
  [Security, privacy, accessibility, reliability, DoD]

TIN HIEU TIEN TRIEN:
  [Increment, phan hoi, outcome co dinh nghia]

KET NOI BACKLOG:
  [Nhung PBI/loai viec dang duoc xep uu tien]

TRIGGER XEM LAI:
  [Feedback moi, Product Goal dat hoac bi tu bo]
~~~

### 17.3. Sprint Goal Test

Trước khi bắt đầu Sprint, đội có thể thử:

~~~text
SPRINT GOAL:
  [Mot muc tieu co nghia cho Sprint]

VI SAO CO GIA TRI:
  [Dong gop Product Goal / giam rui ro]

CO THE KIEM CHUNG:
  [Hanh vi/nguyen tac/kha nang can co]

INCREMENT / DOD:
  [Phan mem dung duoc va dieu kien chat luong]

DIEU DOi CO THE THICH UNG:
  [Phuong an ky thuat, pham vi PBI duoc lam ro]

DIEU KHONG DUOC DANH DOI:
  [DoD, bao mat, tinh dung dan]

PHU THUOC:
  [API, vendor, moi truong, quyet dinh]

NEU KHONG DAT:
  [Bao su that, inspection va adaptation]
~~~

Nếu mục “vì sao có giá trị” chỉ là “để đạt velocity” hoặc mục “có thể kiểm chứng” chỉ là “đã kéo 20 ticket sang Done”, cần xem lại Sprint Goal.

### 17.4. Sprint Review Evidence Sheet

~~~text
PRODUCT GOAL CONTEXT:
  [Ket qua dai han]

SPRINT GOAL:
  [Muc tieu ngan han]

INCREMENTS DAT DOD:
  [PBI/capability va evidence tren build]

PHAM VI CHUA DONG:
  [Nhung phan chua dat DOD, ly do, rui ro]

PHAN HOI THUC:
  [Nguoi dung/stakeholder quan sat gi?]

GIA DINH BI THACH THUC:
  [Dieu gi khac voi du doan?]

THAY DOI MOI TRUONG:
  [Doi tac, quy dinh, ky thuat, du lieu]

QUYET DINH PRODUCT BACKLOG:
  [Uu tien tiep theo do ai chiu trach nhiem?]

GUARDRAILS:
  [Quality, security, release considerations]
~~~

Mẫu này không buộc Sprint Review phải điền từng dòng như báo cáo hành chính. Nó chỉ giúp tránh **Review không có bằng chứng Increment hoặc không tạo điều chỉnh gì**.

### 17.5. Retrospective Experiment Card

~~~text
OBSERVED PROBLEM:
  [Item bi blocked, test muon, queue, handoff...]

EVIDENCE:
  [Item history, DoD, quan sat, su co]

HYPOTHESIS:
  [Neu doi mot co che X, ky vong tin hieu Y]

SMALL EXPERIMENT:
  [Thu trong pham vi nao, ai giup, khi nao?]

METRIC DEFINITIONS:
  [Start/Done, work type, window, data quality]

GUARDRAILS:
  [Khong ha DoD, khong che loi]

POSSIBLE OTHER CAUSES:
  [Work mix, capacity, CI, vendor...]

REVIEW:
  [Giu, sua, dung, mo rong]
~~~

### 17.6. Decision record khi chọn Scrum thay vì Kanban

~~~text
QUYET DINH:
  Thu Scrum cho product team ghi danh;
  dung Kanban cho luong support nen tang.

LY DO:
  Product team can Product Goal + Sprint Goal +
  Increment + inspection cadence.
  Support team co cong viec den lien tuc va can flow policies.

DIEU KIEN:
  PO quyen uu tien, DoD, CI, user feedback,
  WIP policies va cac rui ro khac.

THU NGHIEM:
  Product team qua mot so Sprints co evidence;
  Support team quan ly WIP/SLE va service reviews.

DO LUONG:
  Product outcome/Increment/quality/flow;
  Support service outcome/quality/WIP/age/cycle time.

KHONG KET LUAN:
  Khong dung story points de so hai teams.

TRIGGER XEM LAI:
  Hinh thai cong viec doi, DoD khong duoc dap ung,
  hoac cac chi so co y nghia khong cai thien.
~~~

### 17.7. Một mẫu thông báo tiến triển trung thực

**Thông báo kém:**

> “Chúng ta đã Scrum hóa 100%, đạt velocity 42 points và tổ chức đủ bốn events.”

**Thông báo có ích hơn:**

> “Đội đang thử Scrum để tập trung vào Product Goal ghi danh tự phục vụ. Trong Sprint gần nhất, Increment cho luồng đăng ký miễn phí đã đạt DoD; luồng thanh toán chưa đạt vì contract đối tác chưa được kiểm chứng. Sprint Review cho thấy trạng thái PENDING còn gây nhầm lẫn. Product Owner ưu tiên làm rõ trạng thái và quy tắc quyền; đội thử bổ sung contract tests ở CI để giảm phát hiện lỗi muộn. Dữ liệu outcome hiện chưa đủ cửa sổ quan sát để kết luận hiệu quả toàn bộ sản phẩm.”

Thông báo thứ hai cho lãnh đạo biết **điều gì có giá trị, rủi ro nào còn mở và cần hỗ trợ quyết định gì**.

## 18. Workshop 90 phút: chọn Scrum theo mục tiêu và nhịp kiểm tra, không theo sở thích

Workshop này là **hoạt động học tập gợi ý**, không phải một Scrum event hay điều kiện bắt buộc để được sử dụng Scrum. Có thể tổ chức với Product Owner, Developers, Scrum Master hoặc facilitator, người phụ trách chất lượng/vận hành và stakeholders phù hợp.

### 18.1. Đề bài

Một công ty có hai nhóm:

**Nhóm Sản phẩm A — Ghi danh khóa học:**

- Có một Product Goal sơ bộ nhưng chưa thống nhất với người học.
- Backlog có 30 yêu cầu, phần lớn là UI/API rời rạc.
- Có thể hoàn tất hành vi nhỏ trong khoảng một tới hai tuần nếu môi trường ổn định.
- Stakeholders sẵn sàng review sản phẩm hai tuần một lần.
- Phần quyền học thường lỗi khi tích hợp.

**Nhóm Dịch vụ B — Platform Support:**

- Nhận sự cố build runner, yêu cầu môi trường và hỗ trợ deploy liên tục.
- Những việc khẩn xuất hiện không theo lịch.
- Người dùng chính là các product teams.
- Nhóm có thể đo thời gian chờ, chất lượng dịch vụ và WIP.
- Một số năng lực mới cần phát triển theo roadmap riêng.

Lãnh đạo muốn **cả hai cùng làm Scrum Sprints hai tuần và báo velocity** để dễ so sánh.

**Nhiệm vụ của người học:** đề xuất phương pháp cho từng nhóm, nêu giả thuyết, điều kiện cần và bằng chứng đánh giá. Một đề xuất “Scrum cho A, Kanban cho B” **chỉ đạt khi được giải thích**; một lựa chọn khác có thể hợp lý nếu các giả định và ràng buộc được trình bày nhất quán.

### 18.2. Giai đoạn làm việc

| Thời lượng | Hoạt động | Đầu ra |
|---|---|---|
| **0–10 phút** | Nêu vấn đề người dùng/dịch vụ và cách đang tạo giá trị | Product/service boundary |
| **10–25 phút** | Áp dụng bảy câu hỏi chẩn đoán | Bảng điều kiện và bất định |
| **25–40 phút** | Chọn approach, nêu lý do theo cơ chế | Decision record |
| **40–55 phút** | Với nhóm chọn Scrum: viết Product Goal, Sprint Goal, DoD và Increment khả thi | Một cấu trúc Sprint có ý nghĩa |
| **55–65 phút** | Với nhóm flow: định nghĩa workflow, WIP/age/expedite | Service policies minh họa |
| **65–75 phút** | Chọn metrics và guardrails, phản biện nguy cơ gaming | Một scorecard cân bằng |
| **75–85 phút** | Thiết kế pilot và sự kiện cần xem lại quyết định | Giả thuyết, owner, thời điểm |
| **85–90 phút** | Chia sẻ điều không biết và điều kiện còn thiếu | Kết luận có giới hạn |

### 18.3. Thẻ thông tin phát sinh

**Thẻ A — Product Owner thiếu quyền:** quản lý marketing có thể giao việc trực tiếp cho Developers của nhóm A vào giữa Sprint.

Yêu cầu nhóm thảo luận: còn có thể bảo vệ Sprint Goal không? Cần thay đổi decision rights nào trước/suốt pilot?

**Thẻ B — Đổi DoD:** trước đây Done nghĩa Code Complete; từ tuần này Done phải có integration/security checks.

Yêu cầu nhóm thảo luận: so cycle time/throughput trước–sau thế nào để không kết luận sai?

**Thẻ C — Sự cố nghiêm trọng ở nền tảng:** nhóm B nhận một incident khiến toàn công ty không deploy được.

Yêu cầu nhóm thảo luận: chính sách expedite và trách nhiệm xử lý ra sao? Có nên giữ Sprint Goal cố định nếu nhóm thực chất là dịch vụ incident?

**Thẻ D — Thiếu contract entitlement:** UI của nhóm A đã Done nhưng Learning API hiểu sai trạng thái PENDING.

Yêu cầu nhóm thảo luận: có Increment đạt DoD chưa? Cần thêm năng lực kỹ thuật và phối hợp nào?

**Thẻ E — Outcome đến muộn:** học viên cần 24 giờ sau ghi danh mới có đủ thời gian vào bài; báo cáo lập ngay cuối ngày.

Yêu cầu nhóm thảo luận: làm sao không tính cohort chưa trưởng thành là thất bại?

**Thẻ F — Deadline cố định:** trường cần mở ghi danh trước ngày khai giảng, nhưng chưa xác minh hai phương thức thanh toán.

Yêu cầu nhóm thảo luận: cách kiểm tra mỗi Sprint và thương lượng phạm vi nào có thể bảo vệ DoD và deadline?

### 18.4. Rubric đánh giá

| Tiêu chí | Chưa đạt | Đạt | Tốt |
|---|---|---|---|
| **Chẩn đoán** | Chọn vì phổ biến/đội đã quen | Nêu mục tiêu, loại việc và điều kiện | Có dữ liệu flow, quyền, dependency và rủi ro |
| **Scrum understanding** | Chỉ mô tả Sprint/Daily | Có PO, Product Goal, Sprint Goal, DoD, Review | Phân biệt artifacts, commitments, release và inspection |
| **Kanban understanding** | Chỉ vẽ bảng cột | Có workflow, WIP và policies | Có age, cycle time, SLE và chất lượng |
| **Increment** | Demo mock được gọi Done | Có lát cắt có thể dùng đạt DoD | Có kiểm chứng rủi ro, CI và phản hồi người dùng |
| **Quyền và phụ thuộc** | “Mọi người cùng chịu trách nhiệm” | Có người quyết định và owner | Phân biệt sản phẩm, dịch vụ và guardrails |
| **Metrics** | Chỉ so velocity/ticket count | Có flow và outcome | Metric contract, cohort, chất lượng và bất định |
| **Pilot** | Áp toàn công ty ngay | Có thử nghiệm nhỏ và xem lại | Nêu điều kiện giữ/sửa/dừng, giới hạn nhân rộng |

**Đầu ra tốt nhất không phải nhiều thuật ngữ Scrum nhất**, mà là một quyết định có thể hành động, đúng với sản phẩm/dịch vụ và có bằng chứng để xem lại.

### 18.5. Mẫu câu trình bày cuối workshop

> “Chúng tôi chọn thử **[Scrum/Kanban/cách khác]** cho **[product/service boundary]** vì vấn đề chính là **[mục tiêu phân tán / flow liên tục / chất lượng tích hợp]**. Cơ chế mong đợi là **[Sprint Goal và Review / WIP–pull–feedback / CI và test]**. Điều kiện còn thiếu là **[quyền, DoD, môi trường, hợp đồng]**. Trong **[vài Sprint/kỳ flow]**, chúng tôi kiểm tra **[Increment, quality, work item age, outcome]** với **[metric definitions và guardrails]**, rồi quyết định giữ hoặc sửa dựa trên kết quả.”

Đây là cách thuyết trình giúp lãnh đạo hỗ trợ **đúng ràng buộc**, thay vì yêu cầu mọi đội “đạt 100% compliance với một framework”.

## 19. Bài tập vận dụng

### Bài tập A — Nhận diện vì sao Scrum phù hợp

Một nhóm phát triển ứng dụng học có Product Owner thực quyền, một Product Goal rõ và khả năng tạo lát cắt sử dụng được mỗi một đến hai tuần. Người học và chủ khóa sẵn sàng cùng kiểm tra các kết quả qua nhịp đều đặn.

**Yêu cầu:** Nêu ít nhất ba lý do Scrum đáng cân nhắc và hai điều kiện không thể bỏ.

<details>
<summary>Gợi ý đáp án</summary>

Scrum phù hợp vì nhóm cần mục tiêu chung (Product Goal/Sprint Goal), có khả năng tạo Increment nhỏ, stakeholders có thể kiểm tra và thích ứng thường xuyên, PO có quyền điều chỉnh Product Backlog theo phản hồi. Cần giữ Scrum Team self-managing/cross-functional theo phạm vi thực và Definition of Done tạo Increment dùng được; cũng cần Scrum events có ý nghĩa. Không chỉ tổ chức Daily là đủ.

</details>

### Bài tập B — Dòng incident có nên ép Sprint Goal?

Một nhóm trực vận hành liên tục nhận sự cố với độ nghiêm trọng khác nhau. 70% công việc trong một giai đoạn là yêu cầu khẩn; không có một mục tiêu sản phẩm ngắn hạn ổn định.

**Yêu cầu:** Đề xuất cách tiếp cận và nêu một điều có thể khiến quyết định đổi về sau.

<details>
<summary>Gợi ý đáp án</summary>

Kanban với Definition of Workflow, policies về WIP, classes of service/expedite, work item age, throughput, cycle time và service review có thể phù hợp hơn vì dịch vụ chính là xử lý việc đến liên tục. Con số 70% ở đây là ngữ cảnh, không phải ngưỡng phổ quát. Nếu nhóm sau đó có năng lực riêng xây một platform product với Product Goal, Increment và stakeholder review đều đặn, Scrum có thể đáng thử cho phạm vi phát triển ấy. Vẫn cần quality/reliability guardrails.

</details>

### Bài tập C — Product Goal và Sprint Goal

Đội viết:

~~~text
Product Goal: 30 APIs va 12 man hinh
Sprint Goal: Hoan thanh 50 story points
~~~

**Yêu cầu:** Viết lại thành mục tiêu hướng giá trị có thể kiểm chứng cho nền tảng học.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ Product Goal: “Học viên đủ điều kiện tự ghi danh và vào bài đầu theo đúng quyền trên các luồng được hỗ trợ.” Sprint Goal: “Một học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu qua một Increment tích hợp đạt DoD.” Một nhóm chỉ có khóa trả phí nên chọn lát cắt thanh toán hợp lệ khác thay vì luồng miễn phí giả tạo. Các chỉ số outcome, tính đúng đắn, cohort và DoD phải được nêu phù hợp; points không phải mục tiêu.

</details>

### Bài tập D — Điều gì là commitment của Sprint Backlog?

Trong Sprint Planning, Developers chọn sáu PBI, có Sprint Goal là “Học viên thấy trạng thái đơn đáng tin”. Sau đó phát hiện hai PBI lớn hơn dự đoán.

**Yêu cầu:** Đội có được làm rõ/thương lượng phạm vi không? Điều gì phải bảo vệ?

<details>
<summary>Gợi ý đáp án</summary>

Sprint Goal là **commitment của Sprint Backlog**. Khi hiểu thêm, phạm vi có thể được làm rõ và thương lượng với Product Owner, Developers điều chỉnh kế hoạch hướng Sprint Goal. Không làm thay đổi gây nguy hại mục tiêu hoặc giảm chất lượng. Không cần giả rằng mọi PBI được chọn là hợp đồng chắc chắn, nhưng cũng không tùy tiện bỏ mục tiêu hay coi hạng mục chưa đạt DoD là Done.

</details>

### Bài tập E — Phân biệt Sprint Review và phát hành

Một Increment đã đạt DoD vào ngày thứ sáu của Sprint hai tuần. Product Owner và Developers có điều kiện phát hành an toàn. Quản lý yêu cầu chờ Sprint Review ngày thứ mười mới được release vì “Scrum chỉ release sau Review”.

**Yêu cầu:** Giải thích quy tắc đúng theo Scrum và những điều vẫn cần kiểm tra.

<details>
<summary>Gợi ý đáp án</summary>

Scrum Guide không coi Sprint Review là gate phê duyệt release. Increment đạt DoD có thể được cung cấp trước cuối Sprint; có thể có nhiều Increments trong một Sprint. Tuy nhiên, release vẫn tuân theo chính sách, pháp lý, bảo mật, vận hành và quyền quyết định áp dụng. Done, released và người dùng đạt outcome là ba mốc khác nhau. Không phải cứ đạt DoD là tự động triển khai cho mọi người dùng.

</details>

### Bài tập F — Timeboxes trong Scrum

Nhóm có Sprint hai tuần. Một thành viên tuyên bố Scrum Guide bắt buộc Sprint Review phải kéo dài bốn giờ và Daily Scrum phải là họp báo cáo cho Scrum Master.

**Yêu cầu:** Chỉnh hai phát biểu.

<details>
<summary>Gợi ý đáp án</summary>

Daily Scrum là event **15 phút cho Developers** kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog, không phải buổi báo cáo cá nhân cho Scrum Master. Sprint Review được timebox **tối đa bốn giờ cho Sprint một tháng**, thường ngắn hơn với Sprint ngắn hơn; không phải bắt buộc dùng hết bốn giờ. Tác dụng inspection/adaptation quan trọng hơn dùng đủ phút.

</details>

### Bài tập G — Sprint Goal không đạt

Đội không đạt Sprint Goal do thiếu một hợp đồng API. Quản lý đề xuất đổi nội dung Sprint Goal trong báo cáo cuối để nó khớp hai PBI Done, rồi tính 100% Sprint Goals đạt.

**Yêu cầu:** Nêu vì sao không nên và cách phản hồi tốt hơn.

<details>
<summary>Gợi ý đáp án</summary>

Đổi mục tiêu sau kết quả làm mất minh bạch, ngăn inspection và khuyến khích mục tiêu giả. Cần báo Sprint Goal chưa đạt, những Increments/PBI nào thật sự đạt DoD, blocker API xuất phát từ đâu, làm rõ phụ thuộc sớm trong refinement thế nào và chọn thử nghiệm cải tiến. Một Sprint Goal không đạt là bằng chứng cần học, không phải lý do tự kết luận mọi người thất bại.

</details>

### Bài tập H — Vẫn có Sprint Goal khi có việc ngoài kế hoạch?

Đội đang làm một lát cắt ghi danh, đồng thời xuất hiện một lỗi nghiêm trọng về quyền truy cập production.

**Yêu cầu:** Đội cần giữ nguyên Sprint Backlog mọi giá không? Scrum có cấm xử lý incident?

<details>
<summary>Gợi ý đáp án</summary>

Scrum không cấm xử lý sự cố nghiêm trọng. Đội cần giảm ảnh hưởng theo quy trình thích hợp, minh bạch tác động tới Sprint Goal và điều chỉnh kế hoạch với Product Owner khi cần. Chất lượng không được giảm. Nếu nhiều sự cố chi phối liên tục và không thể bảo vệ một Sprint Goal có nghĩa, cần xem lại policy, năng lực on-call hoặc cách tiếp cận flow khác. Một sự cố đơn lẻ không chứng minh Scrum không phù hợp.

</details>

### Bài tập I — Những điều bắt buộc khi nhiều Scrum Teams cùng sản phẩm

Ba Scrum Teams cùng phát triển một sản phẩm học viên. Team UI, Team API và Team QA có ba Product Owners và ba backlogs ưu tiên riêng.

**Yêu cầu:** Nếu vẫn xác định đây là một Scrum product, điều gì cần chung theo Scrum Guide? Có bắt buộc một Sprint Goal giống nhau cho cả ba teams không?

<details>
<summary>Gợi ý đáp án</summary>

Các Scrum Teams cùng một sản phẩm phải chia sẻ **Product Goal, Product Backlog, Product Owner và Definition of Done**. Product Owner là một người chịu trách nhiệm giá trị, có thể ủy quyền tác vụ chứ không chia thành ba accountabilities độc lập. Các teams cần tạo Increment tích hợp có thể sử dụng. Scrum Guide không yêu cầu mọi Scrum Team có Sprint Goal giống hệt; mỗi team có Sprint Goal của mình nhưng cùng hướng Product Goal và DoD chung. Cần xem team boundaries/cross-functional khả năng tạo giá trị, tránh chia theo tầng gây hàng chờ.

</details>

### Bài tập J — Kanban có thể bổ sung Scrum không?

Một Scrum Team có Sprint Goal rõ nhưng có tám PBI cùng ở In Progress và ba PBI đã blocked hơn mười ngày.

**Yêu cầu:** Nêu ba thực hành Kanban phù hợp mà không bỏ Scrum events/commitments.

<details>
<summary>Gợi ý đáp án</summary>

Định nghĩa rõ workflow Started/Finished, trực quan hóa WIP và blocked; áp dụng WIP control và ưu tiên giúp item gần Done; theo dõi work item age cùng cycle time/throughput và SLE có dữ liệu hỗ trợ để phát hiện điểm nghẽn. Dùng thông tin ở Daily Scrum/Retrospective để thích ứng kế hoạch và policies. Không biến Sprint Goal thành “tăng throughput”, không đếm các subtask như Increment và không bỏ Scrum events nếu vẫn dùng Scrum.

</details>

### Bài tập K — Median cycle time che item còn mở

Một Scrum Team có năm PBI Done với cycle time **2, 3, 4, 5, 6 ngày**; ba PBI đang mở có work item age **12, 17, 22 ngày**.

**Yêu cầu:** Tính median cycle time của item Done và viết câu kết luận trung thực.

<details>
<summary>Gợi ý đáp án</summary>

Median của năm PBI Done là **4 ngày**. Cần báo kèm ba item mở có age 12/17/22 ngày, kiểm tra blocked/DoD và loại công việc. Không nói “mọi item đều mất bốn ngày” hoặc “Scrum đã loại bỏ điểm nghẽn”, vì mẫu chỉ gồm item hoàn tất và có nguy cơ survivorship bias. Cần xem nhiều kỳ cùng metric contract.

</details>

### Bài tập L — Velocity khác đội

Team A có velocity 42 points, Team B 24 points. Giám đốc muốn nhân hệ số để thưởng Team A.

**Yêu cầu:** Phản biện và đề xuất cách đánh giá tốt hơn.

<details>
<summary>Gợi ý đáp án</summary>

Story points thường là thang tương đối nội bộ, khác cách ước lượng, work mix, DoD và bối cảnh; không thể suy Team A năng suất hơn \((42/24-1)\times100\%=75\%\) từ những con số này. Cần xem outcome theo sản phẩm, Increment có thể sử dụng, chất lượng, flow trong cùng boundary và rủi ro/điểm nghẽn. Velocity có thể hỗ trợ một team dự báo nội bộ khi lịch sử đủ ổn định, không dùng làm bảng xếp hạng.

</details>

### Bài tập M — Một PBI bị phân làm bốn task

Trước chuyển đổi, đội đếm **10 PBI Done**. Sau chuyển đổi, cùng loại công việc được tách thành task UI/API/database/test và dashboard báo **28 ticket Done**.

**Yêu cầu:** Có thể nói throughput tăng 180% không? Nên so thế nào?

<details>
<summary>Gợi ý đáp án</summary>

Không thể so 10 PBI với 28 task như cùng đơn vị. Cần định nghĩa item được đo (PBI đạt DoD hoặc work item của một Definition of Workflow), tránh đếm parent/subtask trùng và so cùng loại việc/DoD/cửa sổ. Task nhỏ hơn có thể giúp flow và feedback, nhưng kết luận đúng là “ticket được chia và hoàn tất nhiều hơn”, không tự thành năng suất hay giá trị tăng 180%.

</details>

### Bài tập N — Pilot Scrum với quá nhiều thay đổi đồng thời

Trong ba Sprint, đội đổi từ Kanban sang Scrum, đồng thời thêm hai Developers, nâng CI và chuyển sang nhiều bug UI nhỏ. Median cycle time giảm.

**Yêu cầu:** Viết một đoạn báo cáo đúng mức bằng chứng và một kế hoạch học tiếp.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ: “Giai đoạn thử Scrum có median cycle time của các item Done giảm, nhưng nhân lực, CI và cơ cấu công việc cũng thay đổi; chưa thể quy toàn bộ mức giảm cho Scrum. Đề xuất so các PBI cùng loại/DoD, xem work item age của item chưa Done, quality/outcome và kiểm tra Sprint Review có dẫn tới quyết định sản phẩm không. Sau thêm vài chu kỳ, quyết định giữ hay điều chỉnh cách làm theo evidence.” Không nói “Scrum làm nhanh hơn chính xác X%” nếu không có căn cứ nhân quả.

</details>

### Bài tập O — Cửa sổ outcome chưa đủ

Outcome là tỷ lệ học viên vào bài đầu trong **24 giờ sau xác nhận ghi danh**. Báo cáo chốt 17:00 thứ Sáu nhưng tính học viên vừa xác nhận lúc 16:58 là “không vào bài trong 24 giờ”.

**Yêu cầu:** Lỗi đo lường là gì, sửa ra sao?

<details>
<summary>Gợi ý đáp án</summary>

Đây là trường hợp cohort chưa có đủ thời gian theo dõi, thường gọi là **immature cohort/right censoring**. Người vừa xác nhận mới có hai phút, không thể được gắn thất bại 24 giờ. Có thể chỉ đưa vào mẫu cohort đã có đủ cửa sổ theo định nghĩa, hoặc dùng phương pháp thời gian thích hợp; công bố cutoff, late events, tử/mẫu số và điều kiện loại trừ nhất quán. Không chọn cách loại sau khi nhìn kết quả để làm số đẹp.

</details>

### Bài tập P — Phân biệt Increment và prototype

Một Sprint có bản demo trạng thái thanh toán dùng mock dữ liệu, chưa có test phân quyền hoặc kiểm tra API thật. Stakeholder khen vì giao diện đẹp.

**Yêu cầu:** Kết quả nào hữu ích, điều gì không được báo là Done?

<details>
<summary>Gợi ý đáp án</summary>

Prototype có thể là bằng chứng discovery hoặc usability feedback, giúp học về thiết kế. Nhưng nếu chưa đáp ứng DoD sản phẩm, chưa tích hợp quyền/API thì không được báo là Increment Done. Đội có thể dùng feedback để cải thiện Product Backlog, đồng thời cần kế hoạch kỹ thuật và kiểm chứng rủi ro trước khi Increment có thể sử dụng hoặc được phát hành.

</details>

### Bài tập Q — Deadline cố định và độ bất định

Một trường cần mở cổng ghi danh vào ngày 1 tháng 9. Yêu cầu ban đầu gồm năm phương thức thanh toán, ứng dụng di động mới và dashboard doanh thu; đối tác thanh toán thứ năm chưa có hợp đồng kỹ thuật.

**Yêu cầu:** Scrum có thể giúp gì và không thể bảo đảm gì? Đề xuất cách ưu tiên có trách nhiệm.

<details>
<summary>Gợi ý đáp án</summary>

Scrum có thể giúp nhóm hướng Product Goal, chia PBI theo lát cắt, tạo Increments đạt DoD, inspect/adapt mỗi Sprint và làm rõ phạm vi có giá trị để đáp ứng deadline. Không bảo đảm mọi tính năng đều Done với nguồn lực/ngày cố định khi còn phụ thuộc chưa kiểm chứng. Nên ưu tiên khả năng ghi danh an toàn tối thiểu cho các luồng bắt buộc, làm rõ quy tắc hợp đồng với đối tác, tách phần tùy chọn nếu được quyền, dự báo theo evidence và giữ quality/contractual guardrails. Nếu phạm vi không thể giảm, cần thương lượng nguồn lực/thời gian/rủi ro theo thẩm quyền.

</details>

### Bài tập R — Điều kiện để thay Scrum bằng cách khác

Sau nhiều Sprint, một đội thấy hầu hết công việc là xử lý các yêu cầu dịch vụ khẩn đến bất ngờ. Sprint Goals liên tục lỗi thời và việc quan trọng nhất là đáp ứng service expectations, trong khi đội vẫn muốn có cuộc review hàng tháng.

**Yêu cầu:** Đội có thể chọn Kanban và vẫn review định kỳ không? Những giá trị/thực hành nên giữ?

<details>
<summary>Gợi ý đáp án</summary>

Có. Kanban có thể được chọn cho dòng yêu cầu liên tục, dùng Definition of Workflow, WIP, explicit policies, age/throughput/cycle time, SLE và service reviews; hoàn toàn có thể có nhịp review định kỳ theo nhu cầu mà không gọi đó là Sprint Review của Scrum. Đội vẫn nên giữ mục tiêu dịch vụ/người dùng, chất lượng, CI/tests, feedback và retrospective/improvement khi hữu ích. Cần nêu trung thực cách làm, quyền quyết định và điều kiện xem lại, không xem đổi framework là thất bại của cá nhân.

</details>

## 20. Checklist tự đánh giá trước khi chọn Scrum

Checklist dùng cho cuộc trao đổi **chọn phương pháp hoặc đánh giá pilot**. Không phải “bài thi đúng Scrum”, thang đánh giá nhân sự hoặc một tiêu chuẩn trưởng thành bắt buộc. Nên trả lời theo **một dòng sản phẩm/dịch vụ cụ thể**, nêu bằng chứng và điều chưa biết.

### 20.1. Sản phẩm, người dùng và mục tiêu

1. Đội có thể chỉ rõ **sản phẩm** với ranh giới, người dùng và stakeholders không?
2. Có một **Product Goal** mô tả trạng thái tương lai có giá trị nếu dùng Scrum không?
3. Có phân biệt người dùng nhận kết quả gì với danh sách API, màn hình, ticket được giao không?
4. Product Owner có **quyền quyết định thứ tự Product Backlog thực** không?
5. Stakeholders có kênh phản hồi phù hợp và chấp nhận xem lại thứ tự khi có bằng chứng mới không?
6. Đội có thể làm rõ user story/acceptance criteria theo hành vi và rủi ro không?
7. Có thể chia PBI thành **lát cắt có giá trị** thay vì chỉ task UI–API–DB–QA không?
8. Những nghĩa vụ về bảo mật, dữ liệu, pháp lý và accessibility đã được nhận diện chưa?

### 20.2. Nhu cầu về Sprint Goal và nhịp kiểm tra

9. Có **một mục tiêu ngắn hạn có ý nghĩa** giúp đội tập trung tốt hơn việc kéo task tùy tiện không?
10. Sprint Goal có được viết bằng kết quả/khả năng, không chỉ “N tickets/points” không?
11. Sprint Goal có hướng tới Product Goal và tương thích DoD không?
12. Team có thể điều chỉnh chi tiết kế hoạch mà không làm mất ý nghĩa Sprint Goal không?
13. Dòng công việc có cho phép bảo vệ mục tiêu qua phần lớn Sprint, kể cả khi có việc bất ngờ phù hợp không?
14. Stakeholders có thể kiểm tra **Increment thật và kết quả Sprint** theo một nhịp Sprint hợp lý không?
15. Phản hồi ở Review có thể dẫn tới **thay đổi Product Backlog** bằng quyền phù hợp không?
16. Sprint Retrospective có thể tạo thay đổi thực tế về chất lượng/hiệu quả không?
17. Độ dài Sprint được chọn theo cơ hội học và khả năng giao, không chỉ theo lịch báo cáo công ty không?
18. Có hiểu rằng **timebox Sprint không đồng nghĩa ngày release duy nhất** không?

### 20.3. Scrum Team và accountabilities

19. Scrum Team có Product Owner, Scrum Master và Developers theo định nghĩa Scrum không?
20. Đội có khả năng **cross-functional ở cấp tập thể** để tạo giá trị mỗi Sprint không?
21. Developers có quyền tự quản kế hoạch/cách làm trong Sprint theo ranh giới phù hợp không?
22. Scrum Master có hỗ trợ hiệu quả Scrum thay vì chỉ thu báo cáo status không?
23. Các bên có phân biệt PO tối đa hóa giá trị, Developers tạo Increment, Scrum Master giúp hiệu quả Scrum không?
24. Nếu nhiều Scrum Teams cùng một product, có **Product Goal/Backlog/PO/DoD chung** không?
25. Nếu nhiều sản phẩm độc lập, có xác định **service contracts và quyền ưu tiên từng sản phẩm**, không ép tất cả vào một backlog không?
26. Phụ thuộc API, dữ liệu, môi trường, chuyên gia và đối tác có được làm rõ sớm không?

### 20.4. Increment, DoD và kỹ thuật

27. Đội có thể nêu rõ khi nào một PBI **đạt DoD** thay vì chỉ “Code Complete” không?
28. Một Increment có thể sử dụng được tạo và kiểm chứng **trong mỗi Sprint** theo điều kiện sản phẩm không?
29. Có CI/integration/contract tests và môi trường phù hợp với rủi ro, hoặc kế hoạch cải thiện khả thi không?
30. Các điều kiện phân quyền, tính đúng đắn và dữ liệu có được bảo vệ khi đổi phạm vi không?
31. Đội có phân biệt **Done, released và outcome observed** không?
32. Sprint Review có kiểm tra phần mềm thật, không chỉ slides hoặc velocity không?
33. Những PBI chưa đạt DoD có được báo đúng trạng thái, không cộng thành Increment không?
34. Nếu Sprint Goal chưa đạt, đội có dám báo và học thay vì sửa mục tiêu sau khi kết thúc không?
35. Các thay đổi phức tạp có được chia nhỏ và kiểm chứng sớm, thay vì mặc định cần “Sprint tích hợp” cuối cùng không?

### 20.5. Loại công việc và lựa chọn thay thế

36. Công việc chủ yếu có hướng một kết quả sản phẩm, hay phần lớn là **service requests/incident** không thể dự báo?
37. Nếu nhiều việc khẩn, có chính sách phân luồng và ưu tiên theo mức độ nghiêm trọng không?
38. Đội có hiểu Kanban cung cấp **Definition of Workflow, WIP control, explicit policies và flow metrics** không?
39. Có cân nhắc áp dụng Kanban practices bổ sung vào Scrum khi WIP/blocked làm giảm khả năng Done không?
40. Có cân nhắc XP practices như TDD/CI/refactoring để bảo vệ chất lượng Increment không?
41. Có tránh chọn một cách làm vì phòng ban khác đã chọn hoặc vì tên framework hấp dẫn không?
42. Nếu kết hợp phương pháp, có mô tả **quy tắc làm việc và accountabilities thật** thay vì chỉ gắn nhãn “hybrid” không?

### 20.6. Dữ liệu và đánh giá pilot

43. Có ghi **giả thuyết chọn Scrum** về mục tiêu, Increment, phản hồi và outcome không?
44. Baseline có cùng định nghĩa item, Started/Done, cửa sổ và DoD với dữ liệu sau thử không?
45. Có theo dõi WIP và work item age của item chưa Done, không chỉ cycle time của item hoàn tất không?
46. Throughput có tránh trộn ticket, subtask, parent và PBI đạt DoD không?
47. SLE nếu sử dụng có thời lượng và xác suất cùng điều kiện áp dụng rõ không?
48. Story points/velocity có được dùng có giới hạn nội bộ, không so năng suất giữa teams hoặc cá nhân không?
49. Có theo dõi chất lượng, sự cố và các guardrails không thể bị “bù” bằng throughput cao không?
50. Outcome người dùng có định nghĩa cohort, tử/mẫu số, cửa sổ, event và thời điểm chốt không?
51. Có kiểm tra work mix, nhân lực, CI, phụ thuộc và mùa vụ thay đổi cùng thời kỳ pilot không?
52. Có tránh quy mọi cải thiện cho Scrum khi bằng chứng chỉ là trước–sau không?
53. Sau một số Sprint, đội có thể nêu **Increment nào đã giao, feedback nào đã đổi quyết định**, chứ không chỉ event nào đã tổ chức không?
54. Có kế hoạch giữ/sửa/dừng pilot theo điều kiện và người có thẩm quyền, không nhân rộng chỉ vì lãnh đạo muốn thống nhất lịch không?
55. Nếu Scrum chưa phù hợp, đội có thể chọn cách khác **mà vẫn giữ giá trị Agile: feedback sớm, phần mềm hoạt động, cải tiến và chất lượng** không?

**Nếu nhiều điều kiện nền tảng chưa đạt**, hướng khởi đầu thường không phải đổi tên mọi cuộc họp. Hãy chọn **một sản phẩm, một Product Goal, một Sprint Goal đáng kiểm chứng**, hoặc chọn **một service workflow** nếu công việc chủ yếu là yêu cầu liên tục. Làm rõ quyền, DoD, phụ thuộc và dữ liệu rồi thử cách phối hợp phù hợp ở quy mô nhỏ.

## 21. Tổng kết

- **Chọn Scrum vì mục tiêu và nhịp học**, không vì muốn có nhiều cuộc họp hoặc KPI velocity. Scrum phù hợp khi cần Product Goal và Sprint Goal để tập trung, tạo Increment và kiểm tra–thích ứng đều đặn.
- **Product Goal định hướng sản phẩm, Sprint Goal tập trung một Sprint.** Product Goal là commitment của Product Backlog; Sprint Goal là commitment của Sprint Backlog; Definition of Done là commitment của Increment.
- **Scrum dựa trên empiricism**, cần transparency, inspection và adaptation. Một Sprint đều đặn chỉ có ý nghĩa khi mọi người kiểm tra kết quả thật và có quyền điều chỉnh tiếp.
- **Scrum Team có Product Owner, Scrum Master và Developers** với accountabilities riêng; team cross-functional/self-managing. Một Product Owner “trên giấy” và Developers không có quyền điều chỉnh kế hoạch là trở ngại thực sự.
- **Sprint không quá một tháng, độ dài cố định và liên tiếp.** Planning, Daily Scrum, Review và Retrospective phục vụ mục đích khác nhau; không event nào nên bị rút thành báo cáo status.
- **Sprint Review không phải gate release.** Increment đạt DoD có thể được cung cấp khi phù hợp; Done, released và outcome là ba mốc khác nhau.
- **Scope có thể được làm rõ/thương lượng khi học thêm**, nhưng không được thay đổi gây nguy hại Sprint Goal hoặc giảm chất lượng. Không phải mọi PBI dự đoán ban đầu đều là một lời hứa không điều kiện.
- **Scrum cần năng lực kỹ thuật để có Increment.** TDD, CI, contract tests, refactoring và thực hành XP hữu ích khi giảm lỗi và chi phí thay đổi; chúng không phải các kỹ thuật bắt buộc theo Scrum Guide.
- **Kanban có thể phù hợp hơn với dòng yêu cầu liên tục** và bổ sung cho Scrum khi cần kiểm soát WIP, blocked items và service expectations. Không có quy tắc “mọi team phải cùng một framework”.
- **Scrum kém hiệu quả nếu thiếu product boundary, quyền ưu tiên, DoD hoặc khả năng tích hợp.** Cần phân biệt trở ngại cần sửa với trường hợp bản chất công việc không cần Sprint Goal.
- **Đo hiệu quả bằng mục tiêu, Increment, flow, chất lượng và outcome**, không bằng số lần họp, tỷ lệ Sprint Goals đạt một cách máy móc hoặc story points giữa đội.
- **Pilot là một giả thuyết cần kiểm tra.** Nêu điều kiện, thực hành, guardrails, những thay đổi đồng thời và mốc xem lại để quyết định giữ, điều chỉnh hay chọn cách khác.

Khi đứng trước lựa chọn **“có nên dùng Scrum?”**, hãy hỏi:

> **“Đội có một sản phẩm và mục tiêu chung đủ rõ để tập trung không? Có thể tạo Increment đạt DoD trong một nhịp ngắn không? Có stakeholders và quyền quyết định để kiểm tra kết quả rồi điều chỉnh không? Nếu chưa, điểm nghẽn nào phải được sửa — hay Kanban và cách tổ chức khác phù hợp với dòng công việc hơn?”**

Trả lời các câu hỏi ấy bằng **mục tiêu, sản phẩm, dữ liệu và quyền hạn thật** sẽ giúp Scrum trở thành công cụ giao giá trị và học tập, thay vì một lịch họp được áp đặt.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): bốn giá trị nền tảng của Agile, nhấn mạnh tương tác, phần mềm hoạt động, hợp tác khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm thường xuyên, phối hợp kinh doanh–kỹ thuật, chất lượng, nhịp làm việc bền vững và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): nguồn chính thức về Scrum Team, accountabilities, Sprint, Scrum events, artifacts, commitments, Product Goal, Sprint Goal, Increment và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, WIP, throughput, work item age, cycle time và Service Level Expectation.
- [Scrum.org — The Kanban Guide for Scrum Teams](https://www.scrum.org/resources/kanban-guide-scrum-teams): tham khảo cách dùng các thực hành Kanban để cải thiện flow trong Scrum mà không bỏ các accountabilities và events của Scrum.
- [Scrum.org — Evidence-Based Management](https://www.scrum.org/resources/evidence-based-management): góc nhìn thực nghiệm về giá trị và khả năng giao giá trị khi đánh giá cải tiến.
- **Kent Beck & Cynthia Andres — _Extreme Programming Explained: Embrace Change_** (ấn bản thứ hai): các thực hành kỹ thuật và cộng tác XP giúp rút ngắn feedback và thay đổi code an toàn.
- **Kent Beck — _Test-Driven Development: By Example_**: cách dùng vòng Red–Green–Refactor để kiểm chứng hành vi và thiết kế.
- **Daniel S. Vacanti — _Actionable Agile Metrics for Predictability_**: phân tích WIP, cycle time, work item age, throughput và sử dụng dữ liệu dòng công việc có giới hạn.
- **Jeff Patton & Peter Economy — _User Story Mapping_**: cách nhận diện hành trình người dùng, chia lát cắt giá trị và quản lý Product Backlog.
- **Teresa Torres — _Continuous Discovery Habits_**: kết nối khám phá người dùng và những quyết định sản phẩm cần được xem lại khi có bằng chứng.
- **Matthew Skelton & Manuel Pais — _Team Topologies: Organizing Business and Technology Teams for Fast Flow_**: team boundaries, cognitive load, tương tác giữa stream-aligned và platform teams.
- [DORA](https://dora.dev/): tham khảo về năng lực giao phần mềm và reliability; dùng định nghĩa metric theo phiên bản/ngữ cảnh khi đo.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): cấu trúc Given–When–Then giúp làm rõ hành vi và acceptance examples, không thay bằng chứng test chạy thật.
- [W3C Web Accessibility Initiative](https://www.w3.org/WAI/): tài liệu khả năng tiếp cận web, hữu ích khi Definition of Done cần bảo vệ trải nghiệm cho nhiều nhóm người dùng.







