# Biến Sprint Review thành cổng nghiệm thu duy nhất

## 1. Sai lầm điển hình: “Cứ để cuối Sprint khách hàng duyệt”

Một Scrum Team xây dựng nền tảng học trực tuyến. Sprint kéo dài hai tuần; mục tiêu hiện tại là giúp người học đăng ký khóa miễn phí, nhận xác nhận chính xác và mở bài đầu tiên.

Ngày thứ tư, Developers đã tích hợp được luồng đăng ký qua giao diện, API và cơ sở dữ liệu, đồng thời kiểm thử những trường hợp quan trọng. Một đại diện nghiệp vụ có thể xem thử ngay để kiểm tra cách người học hiểu trạng thái xác nhận.

Thế nhưng nhóm nhận chỉ thị:

> “Đừng cho ai xem trước Sprint Review. Đến cuối Sprint khách hàng mới nghiệm thu. Chỉ sau khi được ký ở cuộc họp đó mới đánh dấu Done và cho phát hành.”

Tới ngày Review, khách hàng nhận ra thông báo “Đã xử lý” quá mơ hồ: người học không biết đã đăng ký thành công hay cần thử lại. Vấn đề đáng lẽ có thể được phát hiện từ ngày thứ tư nay phải chờ gần hết Sprint. Trong thời gian đó, nhiều câu chuyện khác tiếp tục sử dụng cùng giả định sai.

Nhóm có thể còn gặp hai tác động:

1. **Giá trị bị giữ trong hàng chờ**: Increment đã đạt chuẩn chất lượng nhưng không được giao cho người dùng chỉ vì một buổi họp chưa diễn ra.
2. **Chất lượng bị đánh đồng với sự đồng ý của người dự họp**: Một demo được khen vẫn có thể thiếu kiểm thử phân quyền, dữ liệu hoặc Definition of Done; ngược lại, một Increment đã Done không tự mất trạng thái đó vì một stakeholder muốn thêm tính năng mới.

Trong module **AGILE_DEVELOPMENT**, chủ đề **Sai lầm thường gặp** này giúp phân biệt ba việc thường bị trộn lẫn: **kiểm tra và thích ứng trong Sprint Review**, **xác nhận chất lượng của Increment theo Definition of Done**, và **phê duyệt phát hành/nghiệm thu theo quy tắc riêng nếu có**.

**Thông điệp trung tâm:** *Sprint Review không phải cổng kiểm tra cuối cùng quyết định phần mềm đã Done hay chưa, và cũng không được dùng làm cổng mặc định giữ giá trị đến cuối Sprint. Nó là cơ hội cộng tác, kiểm tra kết quả và điều chỉnh tương lai.*

## 2. Sprint Review thực sự nhằm mục đích gì?

Theo **Scrum Guide 2020**, mục đích của **Sprint Review** là **kiểm tra kết quả của Sprint và xác định những điều chỉnh trong tương lai**. Scrum Team trình bày kết quả công việc của mình với stakeholders quan trọng và cùng thảo luận tiến độ hướng **Product Goal**.

Buổi Review không chỉ là trình diễn một chiều. Những người tham gia có thể cùng bàn:

- Phần nào của sản phẩm đã tiến triển và người dùng có thể làm gì?
- Tình hình thị trường, hành vi người dùng hoặc điều kiện kinh doanh có gì mới?
- Giả định nào đã được xác nhận hoặc bị phản bác?
- Product Backlog nên được điều chỉnh ra sao để tăng giá trị?
- Rủi ro và cơ hội nào đáng ưu tiên cho những Sprint tiếp theo?

**Sprint Review là sự kiện làm việc để kiểm tra và thích ứng**, không phải sân khấu để Scrum Team báo cáo đạt bao nhiêu phần trăm hay buổi lễ xin chữ ký cho từng task.

### 2.1. Ba ý chính của Sprint Review

| Ý chính | Diễn giải thực hành | Nếu bị hiểu sai |
| --- | --- | --- |
| **Inspect** | Kiểm tra kết quả thực, tiến triển tới Product Goal và thông tin mới | Chỉ xem slide/tỷ lệ task mà không thử phần mềm |
| **Collaborate** | Scrum Team và stakeholders cùng hiểu giá trị, bất định và lựa chọn | Chỉ một “người duyệt” phát biểu, những người khác nghe |
| **Adapt** | Điều chỉnh Product Backlog hoặc hướng giải quyết khi có cơ sở | Dừng ở “đồng ý/không đồng ý”, không có quyết định sản phẩm |

### 2.2. Vị trí trong chu kỳ Scrum

Sprint Review diễn ra **gần cuối Sprint**, trước **Sprint Retrospective**. Nó không phải sự kiện đầu tiên được phép xuất hiện phản hồi: việc làm rõ Product Backlog, trao đổi với Product Owner, cộng tác với stakeholders và kiểm thử có thể diễn ra trong cả Sprint.

**Scrum không yêu cầu chờ tới Sprint Review mới cho người dùng hoặc Product Owner xem Increment**.

### 2.3. Thời lượng không biến Review thành “hội đồng nghiệm thu”

Với Sprint dài một tháng, Scrum Guide giới hạn Sprint Review trong tối đa **bốn giờ**; Sprint ngắn thường có buổi Review ngắn hơn. Timebox giúp buổi làm việc tập trung vào kiểm tra và thích ứng, **không tạo quyền phê duyệt pháp lý**.

Thời lượng, thành phần dự họp và mẫu biên bản có thể được điều chỉnh theo bối cảnh, nhưng không nên làm mất mục đích sự kiện.

## 3. Nguyên tắc thường bị bỏ qua: Sprint Review không phải cổng phát hành giá trị

Scrum Guide nêu rõ: **một Increment có thể được giao cho stakeholders trước khi Sprint kết thúc, và Sprint Review không được xem như cổng để phát hành giá trị**.

Điều này có hai vế cần đọc cùng nhau:

1. **Không phải đợi cuối Sprint** mới có thể mang phần kết quả đạt chuẩn đến người dùng/stakeholders.
2. **Không có nghĩa mọi Increment phải được đưa lên production ngay**; quy định về bảo mật, vận hành, dữ liệu, kiểm soát rollout hoặc hợp đồng vẫn có thể áp dụng.

### 3.1. “Có thể giao sớm” khác “bắt buộc phát hành mỗi ngày”

Ví dụ:

- Một Increment đạt Definition of Done vào thứ Tư và hệ thống cho phép phát hành an toàn: nhóm **có thể giao trước Review**.
- Increment đạt DoD nhưng rollout phụ thuộc một lịch vận hành đã duyệt: nhóm có thể **giữ trạng thái Done** và phát hành theo chính sách, không giả rằng Sprint Review là quyền duyệt duy nhất.
- Một prototype chưa đạt DoD được đưa cho người dùng thử để học về giao diện: đó là **nguyên mẫu hoặc thử nghiệm có điều kiện**, không được trình bày như Increment Done.

**Đừng biến câu “Review không phải release gate” thành lý do bỏ release policy.** Vấn đề là dùng sai mục đích Scrum Review để thay cho những quyết định có bản chất khác.

### 3.2. Sơ đồ so sánh hai dòng công việc

~~~mermaid
flowchart TD
    subgraph Wrong["Sai lầm: Review là cổng duy nhất"]
        A1["Phát triển và test"] --> B1["Chờ cuối Sprint"]
        B1 --> C1["Sprint Review xin duyệt"]
        C1 --> D1{"Có chữ ký?"}
        D1 -->|"Có"| E1["Đánh dấu Done và cho giao"]
        D1 -->|"Không"| F1["Để lại mọi việc và chờ chu kỳ sau"]
    end
    subgraph Better["Phù hợp hơn: chất lượng, giao giá trị, học hỏi"]
        A2["PBI được phát triển/tích hợp"] --> B2{"Đạt Definition of Done?"}
        B2 -->|"Chưa"| C2["Tiếp tục hoàn thiện và kiểm chứng"]
        C2 --> A2
        B2 -->|"Đạt"| D2["Increment Done"]
        D2 --> E2["Giao/phát hành khi điều kiện áp dụng cho phép"]
        D2 --> F2["Sprint Review: inspect & adapt"]
        E2 --> G2["Phản hồi từ sử dụng"]
        G2 --> F2
        F2 --> H2["Điều chỉnh Product Backlog"]
    end
~~~

Nhánh “Đạt DoD” không miễn các **điều kiện release riêng**. Nhánh Review không nên thay cho kiểm thử, an toàn dữ liệu hoặc quyết định nghiệm thu hợp đồng.

## 4. Definition of Done quyết định tính hoàn tất của Increment

Trong Scrum, **Definition of Done (DoD)** là mô tả chính thức trạng thái của Increment khi nó đáp ứng các thước đo chất lượng cần thiết của sản phẩm. Đây là **commitment của Increment**.

Khi một Product Backlog Item đáp ứng DoD, nó có thể tạo thành một phần Increment. Nếu một PBI **không đáp ứng DoD**, nó không thể được phát hành hoặc thậm chí được giới thiệu tại Sprint Review như **một phần Increment đã Done**; PBI ấy quay lại Product Backlog để được xem xét trong tương lai.

Điểm quan trọng: **người dự Sprint Review không được dùng lời khen hoặc chữ ký để biến công việc chưa đạt DoD thành Done**.

### 4.1. Một DoD minh họa cho sản phẩm học trực tuyến

Tùy sản phẩm và chuẩn tổ chức, DoD có thể bao gồm:

- Mã đã được tích hợp và review theo chính sách.
- Kiểm thử tự động và kiểm thử tích hợp phù hợp với rủi ro đạt.
- Các quy tắc nghiệp vụ được xác minh qua ví dụ chấp nhận.
- Quyền truy cập tài khoản và dữ liệu được kiểm chứng.
- Migration dữ liệu (nếu có) được thử và có cơ chế khôi phục theo quyền.
- Những lỗi nghiêm trọng thuộc phạm vi làm việc đã được xử lý tới tiêu chuẩn áp dụng.
- Tài liệu vận hành, logging và khả năng quan sát cần thiết đã sẵn sàng.
- Không còn điều kiện bắt buộc chưa được đáp ứng để công việc được gọi Done.

**Danh sách là ví dụ**, không phải một DoD Scrum áp dụng mọi sản phẩm. Nếu tổ chức có chuẩn áp dụng cho mọi Scrum Team, DoD phải tuân thủ ít nhất những chuẩn ấy. Nếu nhiều Scrum Teams cùng làm một sản phẩm, chúng cần **cùng định nghĩa và tuân thủ DoD chung**.

### 4.2. Điều không nên nhét vào DoD chỉ để “có người duyệt”

Đôi khi nhóm đặt một bước “đã có chữ ký của khách hàng tại Sprint Review” vào DoD dù yêu cầu này không thuộc chất lượng sản phẩm hoặc chưa phải nghĩa vụ thực. Điều ấy:

- Khiến DoD phụ thuộc **lịch của stakeholder**, không chỉ trạng thái Increment.
- Tạo hàng chờ kể cả khi công việc kỹ thuật đã đạt chuẩn.
- Làm méo throughput, Cycle Time và dự báo vì “Done” bị buộc theo lịch họp.
- Khiến đội khó giao giá trị trước khi Review.

Nếu cần **formal acceptance** theo hợp đồng, hãy quản lý rõ như một quy trình/điều kiện hợp đồng thay vì mặc định đánh đồng với mục đích của Sprint Review. Nếu một yêu cầu chấp thuận là kiểm soát bắt buộc trước một hành động cụ thể, cần tôn trọng nó **ở đúng cổng tương ứng**, không tự xóa.

### 4.3. Câu hỏi kiểm tra trạng thái

Trước khi gọi Done, hãy hỏi:

> “Increment đã đáp ứng DoD của sản phẩm hay chưa?”

Trước khi phát hành, hỏi tiếp:

> “Điều kiện kỹ thuật, vận hành và thẩm quyền áp dụng cho đợt phát hành đã đáp ứng hay chưa?”

Trước khi báo “đã nghiệm thu hợp đồng”, hỏi riêng:

> “Bằng chứng và thủ tục nghiệm thu theo hợp đồng đã hoàn tất bởi người có quyền chưa?”

Ba câu hỏi **không có cùng câu trả lời mặc định**.

## 5. Phân biệt acceptance criteria, DoD, release và nghiệm thu hợp đồng

Chỉ khi tách các khái niệm, nhóm mới có thể tổ chức phản hồi sớm mà vẫn minh bạch trách nhiệm.

| Khái niệm | Mục đích | Cách kiểm tra | Điều không nên suy ra |
| --- | --- | --- | --- |
| **Acceptance criteria** | Làm rõ hành vi mong đợi của một PBI | Ví dụ nghiệp vụ, kiểm thử, trao đổi PO/Developers | Một test PBI xanh nghĩa mọi chất lượng đã đạt |
| **Definition of Done** | Cam kết chất lượng cho Increment Scrum | Bằng chứng chất lượng áp dụng cho sản phẩm | Có chữ ký nghiệm thu pháp lý |
| **Increment** | Phần sản phẩm có thể sử dụng, cộng với các Increment trước và đã được tích hợp | DoD, tính tương thích và sử dụng được | Bắt buộc đã lên production |
| **Release authorization** | Kiểm soát lúc/tại đâu/cho ai triển khai | Gate vận hành, quyền, an toàn, rollout, rollback | DoD có thể được bỏ hoặc Review là cổng mặc định |
| **Sprint Review** | Kiểm tra kết quả Sprint và điều chỉnh tương lai | Cộng tác về Increment, Product Goal, backlog, feedback | Tự động đồng nghĩa release sign-off |
| **Contractual acceptance** | Chấp nhận nghĩa vụ theo tài liệu/thẩm quyền hợp đồng | Tiêu chí, chứng từ, chữ ký/quy trình áp dụng | Cứ demo được là được thanh toán |
| **User outcome** | Đo người dùng có đạt kết quả mong muốn | Sử dụng thực, nghiên cứu, số liệu có ngữ cảnh | Phần mềm đã deploy là giá trị chắc chắn |

### 5.1. Ba phản ví dụ rõ ràng

**Trường hợp A — Đã Done, chưa phát hành:** Increment đăng ký đã đạt DoD, nhưng đợt rollout cho người dùng thật phải chờ một gate bảo mật đã được lên lịch. Trạng thái chất lượng không vì thế trở thành “chưa Done”; phải quản lý sự chờ ở bước release, cùng rủi ro và người có quyền.

**Trường hợp B — Đã demo, chưa Done:** Người học thấy một giao diện có nút đăng ký, nhưng backend chưa ngăn yêu cầu trùng và có lỗi phân quyền. Không thể gọi một phần Increment Done dù màn hình được khen.

**Trường hợp C — Đã giao và được khen, chưa nghiệm thu hợp đồng:** Stakeholder sử dụng thử thành công, nhưng mốc nghiệm thu yêu cầu kiểm thử dữ liệu, tài liệu và người ký được ủy quyền. Sprint Review không tự hoàn thành thủ tục ấy.

### 5.2. Acceptance criteria không là cơ chế chấp thuận pháp lý mặc định

Trong cách làm user story, các tiêu chí chấp nhận cụ thể thường là một phần **Conversation/Confirmation** giúp Product Owner và Developers hiểu cùng một hành vi. Chúng không tự tạo quyền đổi hợp đồng hoặc tự động đáp ứng điều kiện nghiệm thu của một tổ chức.

Ngược lại, nếu hợp đồng quy định một hành vi cụ thể, nhóm cần có cách **truy vết nghĩa vụ đó tới ví dụ và bằng chứng kiểm chứng** phù hợp.

## 6. Hậu quả 1: hàng chờ review nhân tạo làm chậm dòng giá trị

Đặt một cuộc họp cố định làm cổng duy nhất tạo ra **thời gian chờ dù phần mềm đã sẵn**. Tác động có thể thấy rõ trong Cycle Time, lead time từ Done tới sử dụng và thời gian phản hồi.

### 6.1. Ví dụ số học nhỏ

Giả sử một PBI bắt đầu sáng thứ Hai, đạt DoD vào chiều thứ Tư, nhưng Sprint Review chỉ diễn ra thứ Sáu tuần sau.

Để tránh đếm sai, ta quy ước trong ví dụ:

- **Cycle Time theo workflow phát triển:** từ lúc bắt đầu PBI tới lúc đạt DoD; giả sử 3 ngày làm việc.
- **Thời gian chờ release vì lịch Review:** thêm 7 ngày làm việc sau DoD.
- **Thời gian từ bắt đầu tới có thể sử dụng:** \(3+7=10\) ngày làm việc, nếu không có công việc khác hoặc thời gian chồng lắp.

Nếu điều kiện release thực sự cho phép ngay sau DoD, việc giữ 7 ngày chỉ vì muốn đợi Review là **hàng chờ không cần thiết**.

Nhưng không nên cộng 7 ngày vào Cycle Time **nếu định nghĩa kết thúc của Cycle Time là DoD**. Nhóm cần dùng hai phép đo có ranh giới rõ để thấy chậm trễ phát sinh ở đâu.

### 6.2. Biểu đồ giá trị bị giữ lại

~~~mermaid
flowchart LR
    A["PBI bắt đầu"] -->|"3 ngày"| B["Đạt DoD"]
    B -->|"7 ngày chờ họp"| C["Sprint Review"]
    C --> D["Có thể giao nếu đã đủ điều kiện"]
    E["Phương án tốt hơn"] --> F["Đạt DoD"]
    F -->|"Điều kiện release đã đáp ứng"| G["Giao giá trị sớm"]
    G --> H["Phản hồi trước Review"]
    H --> I["Sprint Review giàu dữ liệu hơn"]
~~~

**Thời gian ví dụ hoàn toàn giả định.** Nhiều trường hợp có lý do release hợp lệ ngoài Review; phải xác minh trước khi gọi một khoảng chờ là lãng phí.

### 6.3. Một hệ quả ít được nhìn thấy

Khi nhóm phải chờ cổng duyệt cuối Sprint, mọi người có thể cố “nhồi” nhiều thay đổi trước buổi Review. PR và kiểm thử dồn cuối kỳ, hàng chờ dài, lỗi tích hợp phát hiện muộn. Việc này đi ngược **phản hồi sớm và giao tăng dần** trong Agile.

## 7. Hậu quả 2: chuyển Sprint Review thành buổi xin phép khiến cộng tác kém đi

Khi Review chỉ còn “được duyệt hay không”, các bên dễ rơi vào thế đối đầu:

- Developers muốn chứng minh mọi thứ đã xong để tránh bị bác.
- Stakeholders có thể cảm thấy phải tìm lỗi vào phút cuối vì đây là **cơ hội duy nhất**.
- Product Owner ngại nêu bất định vì có thể bị hiểu là chưa hoàn thành.
- Những ý tưởng mới bị xem thành “lỗi nghiệm thu” thay vì cơ hội học hỏi.
- Mọi người xem phản hồi như một bản án cho công việc đã làm, không phải dữ liệu để định hướng tương lai.

### 7.1. Từ “bị chấm điểm” sang “cùng kiểm tra điều đã học”

| Câu hỏi chỉ nhằm duyệt | Câu hỏi hỗ trợ Review thật |
| --- | --- |
| “Khách hàng có ký cho Done không?” | “Kết quả Done hiện tại giải quyết phần nào của Product Goal?” |
| “Có lỗi nào để trả lại Sprint không?” | “Trong tình huống sử dụng thật, còn điều gì chưa hiểu đúng?” |
| “Đã làm đủ 100% Sprint Backlog chưa?” | “Sprint Goal đã đạt tới mức nào và Increment thực sự cho phép điều gì?” |
| “Có cần ép mọi người cam kết xong hết tuần sau?” | “Thông tin mới làm thứ tự Product Backlog thay đổi thế nào?” |
| “Ai có trách nhiệm khiến stakeholder không thích?” | “Giả định về người dùng, dữ liệu hoặc ngữ cảnh nào cần thử tiếp?” |

### 7.2. Review không phải báo cáo tuần cho quản lý

Một buổi họp chỉ có số ticket, velocity, biểu đồ burndown và slide công việc không chứng minh giá trị đã được kiểm tra. Những số liệu có thể giúp thảo luận, nhưng cần **quan sát Increment và phản hồi bám Product Goal**.

### 7.3. Kết thúc Review nên có hiểu biết và hướng đi

Không nhất thiết phải tạo một “biên bản duyệt” cứng. Đầu ra có ích có thể gồm:

- Điều đã học về giá trị và người dùng.
- Vấn đề mới và rủi ro được nhận diện.
- Những PBI cần làm rõ/thay thứ tự.
- Giả thuyết hoặc thí nghiệm cần thực hiện.
- Quyết định nào đã nằm trong quyền PO/nhóm và quyết định nào cần người có thẩm quyền khác.

## 8. Hậu quả 3: trộn “lỗi” với “mong muốn mới” làm backlog rối

Trong Review, stakeholder nói:

> “Màn hình đăng ký nên gửi email xác nhận nữa.”

Ý kiến này có thể là:

1. **Lỗi so với tiêu chí đã có** nếu email là yêu cầu bắt buộc đã được làm rõ.
2. **Sự chưa rõ phạm vi** nếu các bên từng dùng từ “xác nhận” nhưng chưa thống nhất kênh.
3. **Cơ hội sản phẩm mới** nếu email là một khả năng bổ sung chưa nằm trong phạm vi.
4. **Thay đổi hợp đồng** nếu thêm email làm thay nghĩa vụ, giá, mốc hoặc điều kiện nghiệm thu.

Nếu nhóm gộp cả bốn vào “Review chưa pass”, họ đánh mất thông tin ra quyết định.

### 8.1. Một bảng phân loại phản hồi

| Phản hồi | Câu hỏi phân loại | Hành động phù hợp |
| --- | --- | --- |
| Không thể đăng ký khi mạng chập chờn | Có vi phạm hành vi/DoD đã xác định? | Tái hiện, sửa lỗi, kiểm thử |
| Nút mở bài khó tìm | Có phải vấn đề usability và giá trị? | Nghiên cứu, sửa trong phạm vi nếu phù hợp |
| Muốn email xác nhận | Đã thuộc nghĩa vụ/tiêu chí chưa? | Làm rõ, ưu tiên hoặc trình change request |
| Muốn gợi ý khóa bằng AI | Có là năng lực mới? | Kiểm chứng giá trị, quyền và phạm vi; chưa cam kết |
| Thấy dữ liệu của tài khoản khác | Rủi ro phân quyền, dữ liệu | Bảo vệ người dùng, xử lý theo yêu cầu an toàn và quyền |
| Muốn đổi ngày nghiệm thu | Ảnh hưởng mốc hợp đồng? | Đưa qua chủ thể có quyền quyết định |

**Ghi phản hồi không có nghĩa nhận cam kết làm ngay.** Product Owner quản lý hiệu quả Product Backlog; nếu ràng buộc hợp đồng áp dụng, việc đổi nghĩa vụ phải qua thẩm quyền riêng.

## 9. Hậu quả 4: lỗi chất lượng bị phát hiện muộn hoặc bị “ký cho qua”

Một nhóm lầm tưởng rằng “có khách hàng xem cuối Sprint” là đủ kiểm soát chất lượng. Nhưng Review không thay:

- Unit/integration/contract tests.
- Kiểm thử đồng thời và retry.
- Kiểm thử phân quyền, bảo vệ dữ liệu.
- Review mã và tích hợp liên tục.
- Kiểm thử accessibility hoặc hiệu năng khi là tiêu chuẩn áp dụng.
- Migration/rollback và khả năng vận hành khi cần.

**Một buổi demo chủ yếu đi theo happy path rất khó phát hiện race condition, lộ dữ liệu hoặc vấn đề khi mạng lỗi.**

### 9.1. Ví dụ hỏng đăng ký khi retry

Trong demo, người học bấm “Đăng ký” một lần và nhận trạng thái thành công. Nhưng ở mạng thật, client timeout rồi gửi lại yêu cầu. Hai request có thể tạo hai bản ghi đăng ký đang có hiệu lực nếu tính nhất quán chưa được bảo vệ.

Nếu DoD yêu cầu kiểm thử những trường hợp này mà chưa đạt, nhóm **không có Increment Done cho PBI đó**, dù khách hàng vỗ tay tại Review.

### 9.2. Ba lớp phát hiện

| Lớp | Phát hiện gì? | Ví dụ |
| --- | --- | --- |
| **Tại mã/CI** | Sai quy tắc, regression, hợp đồng kỹ thuật | Unit/contract/integration tests |
| **Tại tích hợp/DoD** | Luồng end-to-end và điều kiện chất lượng | Đăng ký không tạo trùng, phân quyền đúng |
| **Tại phản hồi người dùng/Review** | Giả định giá trị, khả năng sử dụng, điều cần làm tiếp | Người học không hiểu trạng thái hoặc khó mở bài |

Ba lớp **bổ sung nhau**, không thể thay thế đơn giản bằng một cổng duy nhất.

## 10. Hậu quả 5: Product Owner trở thành “người ký Done”

Trong Scrum, Product Owner chịu trách nhiệm **tối đa hóa giá trị sản phẩm** và **quản lý hiệu quả Product Backlog**. Product Owner không được định nghĩa như một “người phê duyệt cuối cùng” có thể bật/tắt trạng thái Done của Increment bằng cảm tính.

Developers chịu trách nhiệm tạo Increment **đáp ứng Definition of Done**. Scrum Master giúp Scrum Team hiểu và áp dụng Scrum hiệu quả. Stakeholders đóng góp phản hồi và thông tin giá trị.

### 10.1. Phân biệt trách nhiệm

| Chủ thể | Trách nhiệm liên quan | Không nên gán nhầm |
| --- | --- | --- |
| **Developers** | Tạo Increment chất lượng, kiểm chứng DoD, thích ứng kế hoạch thực hiện | “Chỉ cần khách hàng thích là được coi Done” |
| **Product Owner** | Product Goal, giá trị và Product Backlog; trao đổi với stakeholders | “Một mình ký thay mọi tiêu chuẩn an toàn/hợp đồng” |
| **Scrum Master** | Hỗ trợ Scrum, gỡ trở ngại và cải tiến hiệu quả | “Chủ tịch hội đồng nghiệm thu” |
| **Stakeholders** | Mang phản hồi, nhu cầu và bối cảnh kinh doanh | “Mọi lời góp ý là lệnh đổi scope” |
| **Release/security/operations** | Điều kiện vận hành/an toàn trong quyền | “Chỉ cần tham gia Review là được phép bỏ gate” |
| **Contract/procurement authority** | Thủ tục thay đổi và nghiệm thu theo hợp đồng nếu có | “Là Product Owner theo định nghĩa Scrum” |

### 10.2. Trường hợp PO chưa thể quyết định một thay đổi

Người dùng yêu cầu chức năng nằm ngoài SOW. PO có thể ủng hộ nó theo giá trị, nhưng **không nhất thiết có quyền sửa hợp đồng hoặc chi thêm ngân sách**. Việc cần làm là ghi phản hồi, phân tích tác động rồi chuyển đúng người phê duyệt.

### 10.3. Tránh cấu trúc “chỉ stakeholder mới được nói chuyện với Developer”

Nếu mọi câu hỏi nhỏ phải đợi Review, Developers dễ xây theo giả định và làm lại. Hãy thiết kế cách cộng tác trong Sprint, đồng thời giữ Product Owner minh bạch về Product Backlog và những quyết định thuộc quyền mình.

## 11. Quy trình đúng hơn: hoàn tất chất lượng, giao khi được phép, học liên tục

Thay vì một cổng “đến Review mới được Done”, thiết kế **những đường trách nhiệm rõ**:

~~~mermaid
flowchart TD
    A["Product Goal và PBI có giá trị"] --> B["Refinement: làm rõ hành vi và rủi ro"]
    B --> C["Developers phát triển/tích hợp/test"]
    C --> D{"Đạt Definition of Done?"}
    D -->|"Chưa"| C
    D -->|"Đạt"| E["Increment Done, có thể sử dụng"]
    E --> F{"Điều kiện release áp dụng đã đáp ứng?"}
    F -->|"Có"| G["Phát hành/giao theo chính sách"]
    F -->|"Chưa"| H["Xử lý gate hoặc lịch release theo quyền"]
    H --> F
    E --> I["Sprint Review: kiểm tra kết quả"]
    G --> J["Phản hồi từ sử dụng thật"]
    J --> I
    I --> K["Thích ứng Product Backlog"]
    K --> B
    E --> L["Bằng chứng nghiệm thu nếu hợp đồng yêu cầu"]
    L --> M["Thủ tục/đại diện có thẩm quyền"]
~~~

**Chú ý:**

- Nhánh **release** và nhánh **Sprint Review** là hai quyết định khác mục đích.
- Nhánh **nghiệm thu hợp đồng** không tự đi qua Review dù có thể dùng chung bằng chứng.
- Phản hồi có thể đến **trước, trong hoặc sau Review**; người học không bị buộc phải đợi buổi họp cuối Sprint mới được nói.
- Nếu có lỗi hoặc rủi ro an toàn đang xảy ra, phải xử lý theo mức độ và quyền; không chờ event định kỳ.

### 11.1. Các câu hỏi nên hỏi ngay khi PBI đạt DoD

1. Phần này có sử dụng được và tích hợp với Increment trước không?
2. Có nhu cầu phát hành hoặc giao sớm để học và tạo giá trị không?
3. Điều kiện release hợp lệ nào còn chưa xong?
4. Có thể thu phản hồi từ người được phép trên dữ liệu an toàn không?
5. Có điều gì cần chia sẻ tại Sprint Review để thảo luận Product Goal?

### 11.2. Không mặc định release sớm luôn tốt hơn

Một thay đổi vào hệ thống thanh toán/đăng ký đang phục vụ nhiều người học có thể cần canary release, giám sát, hỗ trợ và rollback. Nếu tổ chức có lịch phát hành an toàn, cần phối hợp. **Agile khuyến khích giao giá trị sớm trong điều kiện an toàn**, không đòi “deploy bằng mọi giá”.

## 12. Nhận phản hồi sớm trong Sprint không làm mất vai trò Sprint Review

Có nhóm e ngại rằng nếu người dùng đã thử phần mềm vào giữa Sprint thì **cuối Sprint không còn gì để Review**. Đây là cách hiểu sai về giá trị của sự kiện.

**Sprint Review không được tạo ra để giữ phản hồi trong một buổi duy nhất.** Nó giúp Scrum Team cùng các stakeholders quan trọng nhìn bức tranh kết quả Sprint, tiến bộ tới Product Goal và quyết định thích ứng.

### 12.1. Những kênh phản hồi trước Sprint Review

| Kênh | Câu hỏi có thể giải quyết | Điều cần giữ |
| --- | --- | --- |
| **Refinement với người hiểu nghiệp vụ** | Acceptance examples đã rõ chưa? | PO giữ minh bạch Product Backlog và quyền quyết định |
| **Three Amigos / trao đổi BA–Dev–Test** | Trường hợp lỗi, ranh giới và chất lượng nào còn thiếu? | Không biến thành gate duyệt mới |
| **Prototype/usability test** | Người học hiểu giao diện và nhiệm vụ không? | Không gọi prototype là Increment Done |
| **Early Increment preview** | Lát cắt Done có giải quyết đúng nhu cầu không? | Phân biệt preview, release và nghiệm thu |
| **CI, contract tests, integration tests** | Những giả định kỹ thuật còn sai ở đâu? | Dùng test phù hợp rủi ro, không lấy xanh giả |
| **Telemetry/feedback sau release** | Người dùng thật có đăng ký và mở bài được không? | Đảm bảo quyền dữ liệu và cách đo nhất quán |
| **Hỏi đáp trực tiếp khi bị blocked** | Ai cần làm rõ API, dữ liệu hay điều kiện hợp đồng? | Không đợi đến Review mới gỡ blocker |

### 12.2. Một nhịp hai tuần minh họa

| Ngày làm việc | Tình huống | Học hỏi hoặc hành động |
| --- | --- | --- |
| **Ngày 1** | Sprint Planning và làm rõ Sprint Goal | Biết kết quả muốn có, rủi ro, kế hoạch đầu |
| **Ngày 2–3** | Xây lát cắt đăng ký, chạy CI | Phát hiện contract API sai |
| **Ngày 4** | Lát cắt đạt DoD và preview với người dùng được phép | Phát hiện trạng thái xác nhận khó hiểu |
| **Ngày 5** | PO và Developers làm rõ ý nghĩa phản hồi | Sửa trong phạm vi hoặc ghi PBI tiếp theo |
| **Ngày 6–8** | Kiểm thử retry, phân quyền, tích hợp và cải thiện | Giảm rủi ro chất lượng, có thể giao sớm nếu đủ điều kiện |
| **Ngày 9** | Xem dữ liệu từ nhóm học thử | Biết tỷ lệ người đăng ký đã mở bài |
| **Ngày 10** | Sprint Review, rồi Sprint Retrospective | Cộng tác về Product Goal, hướng Product Backlog và cải tiến |

**Nhịp trên chỉ để minh họa**, không quy định một Sprint phải có đúng các hoạt động ở ngày cụ thể. Các sự kiện Scrum cần giữ mục đích và timebox thực tế.

### 12.3. Điều gì được mang tới Review nếu phản hồi đã xảy ra?

Thay vì chỉ diễn lại màn hình, nhóm có thể trình bày:

- Increment nào thực sự Done và đã được sử dụng bởi ai.
- Phản hồi nào đã thu được, có những người dùng nào chưa đại diện.
- Giả thuyết giá trị nào được củng cố hoặc bác bỏ.
- Những thay đổi nào đã được xử lý an toàn, những thay đổi nào còn chờ.
- Các lựa chọn tiếp theo và tác động tới Product Goal.

**Review có thể tốt hơn khi đã có phản hồi thật trước đó**, vì cuộc thảo luận dựa trên bằng chứng sử dụng thay vì chỉ suy đoán trên bản demo.

## 13. Thiết kế Sprint Review như buổi cộng tác, không phải hội đồng chấm điểm

Một buổi Review có thể có cấu trúc, nhưng cấu trúc phải phục vụ **inspect & adapt**. Không cần tấm bảng “Accepted/Rejected” cho từng story làm nội dung trung tâm.

### 13.1. Mẫu agenda cho Sprint hai tuần

Đây là **gợi ý 55 phút**, không phải Scrum Guide bắt buộc:

| Phần | Thời lượng | Câu hỏi chính |
| --- | ---: | --- |
| Mở đầu: Product Goal và bối cảnh | 5 phút | Chúng ta đang theo đuổi điều gì? |
| Sprint Goal và kết quả thật | 10 phút | Mục tiêu đạt tới mức nào? Increment nào Done? |
| Dùng thử phần sản phẩm đã Done | 15 phút | Stakeholders thấy gì, muốn thử tình huống nào? |
| Bằng chứng từ người dùng và vận hành | 10 phút | Điều nào đúng/sai so với giả thuyết? |
| Thảo luận lựa chọn cho tương lai | 10 phút | Product Backlog nên thích ứng ra sao? |
| Kết luận quyết định và việc còn cần xác minh | 5 phút | Ai phối hợp, rủi ro và dữ kiện nào còn thiếu? |

**Không phải mọi stakeholder đều phải dự toàn bộ hoạt động** nếu không liên quan. Quan trọng là những người có góc nhìn giúp ra quyết định sản phẩm cùng có mặt hoặc góp ý được.

### 13.2. Cách mở Review tốt hơn

**Chưa tốt:**

> “Sprint này làm 37/40 points, sau đây nhờ khách hàng nghiệm thu từng ticket để tính hiệu suất.”

**Tốt hơn:**

> “Sprint Goal là giúp người học đăng ký khóa miễn phí và biết cách bắt đầu bài đầu tiên. Lát cắt đăng ký hiện đạt DoD và đã được thử với nhóm người học có quyền. Chúng ta sẽ xem hành vi, phản hồi, những điểm còn bất định và thảo luận thứ tự cần ưu tiên tiếp theo.”

Cách thứ hai đặt **giá trị và kết quả** làm trung tâm, thay vì biến Review thành phiên xử trạng thái task.

### 13.3. Chuẩn bị những bằng chứng thực sự giúp thảo luận

- Một hoặc vài hành trình người dùng **đã đạt DoD**.
- Mục tiêu Sprint, Product Goal và phạm vi bản đang xem.
- Một số tình huống sử dụng bất thường hoặc thất bại đáng chú ý.
- Dữ liệu phản hồi có nguồn và giới hạn.
- Những rủi ro hoặc phụ thuộc có thể ảnh hưởng Product Backlog.
- Các câu hỏi đang cần stakeholder làm rõ hoặc lựa chọn.

**Không cần trình bày log hoặc chi tiết mã cho mọi người**, trừ khi chúng thực sự giúp quyết định. Thông tin cá nhân và dữ liệu nhạy cảm phải được bảo vệ.

### 13.4. Không bỏ qua Sprint Goal

Một Scrum Team có thể hoàn thành nhiều PBI nhưng **Sprint Goal không đạt** vì phần kết quả xuyên suốt chưa sử dụng được. Ngược lại, Sprint Goal có thể đạt dù một số PBI lựa chọn ban đầu được thương lượng lại trong Sprint.

Tại Review, cần minh bạch cả **mục tiêu đã đạt đến đâu** lẫn **Increment thực sự Done**. Không chỉ đọc danh sách ticket.

## 14. Mô tả kết quả Review bằng ngôn ngữ quyết định, không phải dấu đóng duyệt

Nhóm có thể ghi lại kết quả ngắn:

| Quan sát trong Review | Diễn giải | Hành động/đường quyết định |
| --- | --- | --- |
| Người học không thấy nút mở bài | Vấn đề hành trình sử dụng | PO và Developers nghiên cứu/sắp backlog |
| Increment đăng ký có lỗi phân quyền | Lỗ hổng chất lượng; DoD chưa đạt với PBI liên quan | Sửa/test, ứng cứu theo mức rủi ro |
| Một stakeholder muốn gửi email mới | Nhu cầu chưa chắc thuộc phạm vi | Làm rõ giá trị và nghĩa vụ; quyết định quyền |
| Dữ liệu cho thấy activation thấp | Giả thuyết giải pháp cần kiểm chứng | Đề xuất nghiên cứu/thiết kế cải tiến |
| Khả năng báo cáo được yêu cầu trước mốc | Có dependency và nghĩa vụ | Rà soát forecast và thứ tự Product Backlog |
| Hệ thống đã đạt DoD và release policy | Có thể giao phần giá trị | Quyết định release theo cơ chế được phép |

### 14.1. Không cần chờ Review mới xử lý một vấn đề đã rõ

Nếu test phân quyền thất bại trong ngày thứ ba, phải điều tra/sửa ngay theo mức độ và rủi ro. **Không mang một sự cố dữ liệu đang gây hại tới cuối Sprint rồi hỏi stakeholder có “accept” không**.

### 14.2. Không nên cho Product Owner một “nút Accepted” thay toàn bộ chính sách

Product Owner có thể xác nhận hiểu biết về hành vi nghiệp vụ, làm rõ giá trị và điều chỉnh Product Backlog. Nhưng **DoD cần bằng chứng chất lượng**, còn phê duyệt production hoặc hợp đồng theo người có thẩm quyền riêng. Một trường trạng thái “PO Accepted” có thể hữu ích cho việc phối hợp nếu được định nghĩa rõ, **không thay thế trạng thái Done**.

### 14.3. Phân biệt việc quyết ngay với việc cần khảo sát

Một phản hồi nhỏ có đủ dữ liệu có thể làm PO đổi thứ tự Product Backlog sau Review. Một đề nghị thay dữ liệu hoặc điều khoản hợp đồng có thể cần thời gian thẩm định. Buổi Review vẫn hữu ích nếu **xác định đúng câu hỏi, người quyết định và bước tiếp theo**, dù chưa thể ký mọi thứ ngay.

## 15. Khi khách hàng có hợp đồng nghiệm thu: làm hai việc đúng bản chất

Không phải mọi tổ chức có thể phát hành tự do. Đặc biệt trong dự án đấu thầu, mua sắm hoặc môi trường quản lý chặt, **nghiệm thu hợp đồng** có thể là nghĩa vụ bắt buộc với biên bản và người ký được ủy quyền.

Điều đó không làm Sprint Review trở thành **cổng nghiệm thu duy nhất** theo định nghĩa Scrum. Thay vào đó, cần phân biệt **vòng sản phẩm** với **vòng quản trị nghĩa vụ**.

### 15.1. Hai vòng có thể dùng chung bằng chứng

~~~mermaid
flowchart TD
    A["Product Backlog và Increment"] --> B["Đạt DoD"]
    B --> C["Sprint Review: phản hồi, inspect, adapt"]
    C --> D["Product Backlog được làm rõ/điều chỉnh"]
    D --> A
    B --> E["Hồ sơ kiểm thử/bàn giao theo baseline"]
    E --> F["Kiểm tra tiêu chí nghiệm thu hợp đồng"]
    F --> G["Người có thẩm quyền quyết định"]
    G --> H["Trạng thái nghiệm thu/thanh toán theo hợp đồng"]
    B --> I["Đánh giá điều kiện release riêng"]
    I --> J["Giao/phát hành nếu được phép"]
    J --> K["Phản hồi từ sử dụng"]
    K --> C
~~~

Một biên bản Sprint Review có thể ghi **nhận xét và quyết định sản phẩm**, nhưng không nên tự biến thành văn bản “đã nghiệm thu theo hợp đồng” nếu chưa đủ điều kiện.

### 15.2. Ví dụ hợp đồng nền tảng học

Giả sử hợp đồng quy định:

- H-01: Đăng ký khóa và xác nhận.
- H-02: Mở bài đầu và quản lý quyền học.
- H-03: Báo cáo tiến độ.
- H-04: Kiểm thử bảo mật, tài liệu và hồ sơ bàn giao.
- Mốc nghiệm thu cuối kỳ có **người ký theo thẩm quyền**.

Nhóm có thể tổ chức Sprint Review mỗi hai tuần để học từ Increment. Nhưng khi tới mốc nghiệm thu, cần **kiểm tra đủ đầu ra, chứng cứ, tiêu chí, thủ tục và quyền ký**. Một Increment Done trong Sprint 1 không tự chứng minh H-01 đã được nghiệm thu theo hợp đồng, và một đề nghị bỏ H-03 ở Review không tự sửa baseline.

### 15.3. Product Owner khác người được quyền ký nghiệm thu

Product Owner có thể ở phía khách hàng và làm việc rất sát nhóm mỗi ngày. Tuy nhiên, quyền ký biên bản nghiệm thu, thay SOW hoặc duyệt ngân sách là **quyền theo hợp đồng và tổ chức**, không tự đi kèm tên gọi Product Owner.

Một cấu trúc phối hợp tốt sẽ:

1. Cho PO đủ quyền **quản lý hiệu quả Product Backlog**.
2. Cho Developers đủ điều kiện **giao Increment đạt DoD thường xuyên**.
3. Tạo kênh rõ cho **thay đổi nghĩa vụ và nghiệm thu chính thức**.
4. Không buộc người có quyền ký hợp đồng tham gia từng quyết định kỹ thuật hằng ngày.
5. Không yêu cầu Scrum Review gánh mọi thủ tục pháp lý.

### 15.4. Nghiệm thu theo giai đoạn có thể tồn tại độc lập

Nếu hợp đồng **cho phép nghiệm thu từng phần**, nhóm có thể thiết kế các bộ bằng chứng phù hợp với Increment. Tuy nhiên việc nghiệm thu từng phần **chỉ có hiệu lực theo hợp đồng và người có quyền**, không vì một Sprint hoàn tất mà tự động phát sinh.

## 16. Khi có release gate bắt buộc: không xóa gate, không đổi tên nó thành Sprint Review

Một tổ chức quản lý tài chính, dữ liệu nhạy cảm hoặc hệ thống có yêu cầu vận hành cao có thể cần:

- Security/privacy approval.
- Change Advisory Board hoặc quy trình thay đổi vận hành.
- Phê duyệt migration dữ liệu production.
- Kiểm tra accessibility hoặc yêu cầu pháp lý chuyên ngành.
- Lịch phát hành với kế hoạch rollback/incident.
- Quyền triển khai ở môi trường production.

Những ràng buộc ấy có thể hoàn toàn chính đáng.

### 16.1. Gate hợp lệ cần có tiêu chí và quyền rõ

| Câu hỏi | Mục đích |
| --- | --- |
| **Kiểm soát rủi ro nào?** | Không tạo gate chỉ vì thói quen |
| **Bằng chứng nào cần có?** | Test, đánh giá, migration, rollback, dữ liệu |
| **Ai có quyền quyết định?** | Tránh người dự họp ký vượt quyền |
| **Khi nào phải kiểm tra?** | Chuẩn bị sớm, không đợi sát ngày |
| **Có phần nào tự động hóa hợp lệ?** | Giảm chờ không cần thiết |
| **Khi chưa đạt thì sao?** | Rõ phương án sửa, rollback, hoãn và thông báo |

### 16.2. Một Sprint Review có thể trùng lịch gate nhưng không đồng nhất

Nếu doanh nghiệp cố định lịch hội đồng release vào thứ Sáu cuối Sprint, về mặt lịch **có thể trùng ngày Sprint Review**. Nhưng cần giữ mục đích và người quyết định riêng:

- **Review:** Scrum Team và stakeholders inspect & adapt sản phẩm.
- **Release gate:** Người có quyền kiểm chứng điều kiện phát hành.

Có thể nối dữ liệu hoặc tổ chức sát nhau để giảm trùng lặp, nhưng **không biến ý kiến “thích/không thích demo” thành thay thế các kiểm soát an toàn**.

### 16.3. Đẩy việc kiểm tra bắt buộc lên sớm

Đừng chờ cuối Sprint mới nộp tài liệu privacy, test phân quyền hay kế hoạch migration. Phối hợp chuyên gia và tự động hóa những phép kiểm tra được phép **ngay trong quá trình phát triển** giúp khi tới gate có đủ bằng chứng.

### 16.4. Không gọi thời gian chờ release là thời gian Developers “chưa Done”

Nếu Increment đã đạt DoD nhưng còn chờ lịch release, hãy nói minh bạch:

> “Increment Done; chưa phát hành vì chờ gate bảo mật được quy định; ngày quyết định được theo dõi riêng.”

Ngược lại, nếu DoD có những kiểm tra chất lượng bắt buộc chưa đạt, không được gọi Done rồi đổ phần thiếu vào gate.

## 17. Khi nhiều Scrum Teams cùng phát triển một sản phẩm

Với nhiều Scrum Teams cùng một sản phẩm theo Scrum, các nhóm **cùng chia sẻ Product Goal, Product Backlog, Product Owner và Definition of Done**. Mỗi Scrum Team có Sprint Goal và Sprint Backlog riêng, nhưng những phần công việc phải tích hợp thành **Increment của cùng sản phẩm**.

### 17.1. Sai lầm mở rộng: một “Super Sprint Review” ký tất cả các mảnh rời

Giả sử:

- Team A làm giao diện đăng ký.
- Team B làm API enrollment.
- Team C làm ràng buộc database.

Mỗi nhóm báo “Done 100%” tại một cuộc Review chung; khi ghép thật, luồng đăng ký trùng và quyền học sai. **Không có Increment của luồng ấy đạt DoD** dù từng nhóm đã hoàn thành các task cục bộ.

Một cuộc Review có đủ đại diện không làm **các thay đổi chưa được tích hợp** trở thành phần mềm sử dụng được.

### 17.2. Tổ chức tích hợp và phản hồi xuyên ranh giới

Những thực hành hữu ích:

- Cùng làm rõ acceptance examples và ranh giới dữ liệu sớm.
- Giữ **một DoD chung** trong cùng sản phẩm.
- Có CI/contract tests và nhịp tích hợp thường xuyên.
- Làm rõ quyền sở hữu API, phản hồi khi thay đổi hợp đồng giữa consumer/provider.
- Ghi dependency thật thay vì mặc định “bên kia chưa xong”.
- Sử dụng Sprint Review để xem **kết quả tích hợp và Product Goal**, không chỉ các màn hình demo riêng.

### 17.3. Product Backlog chung không đồng nghĩa buộc mọi nhóm cùng một Sprint Goal

Nhiều Scrum Teams có Sprint Goals riêng nhưng căn chỉnh với Product Goal và Increment sản phẩm. Không nên áp một Sprint Goal toàn doanh nghiệp chỉ để tổ chức **một buổi nghiệm thu duy nhất**.

### 17.4. Scrum of Scrums là lựa chọn, không phải cổng duyệt mới

Nhóm có thể dùng đồng bộ liên nhóm hoặc Scrum of Scrums để giải quyết tích hợp, phụ thuộc và rủi ro. Đó là phương tiện bổ sung khi hữu ích, **không phải sự kiện Scrum bắt buộc** và cũng không phải nơi biến task thành Done qua chữ ký đại diện.

## 18. Kanban: nhìn hàng chờ phê duyệt thay vì giấu nó trong cột Done

Kanban hỗ trợ trực quan hóa dòng công việc, giới hạn WIP và quản lý tuổi công việc. Nếu một quy trình có hàng chờ chấp thuận thật, nên **làm nó nhìn thấy được**.

### 18.1. Đừng gộp các trạng thái khác nghĩa

Một workflow có thể biểu diễn:

~~~text
Ready -> Development -> Review code -> Test -> Done (DoD)
                                               |
                                               v
                             Ready for release -> Release gate -> Released

Contract acceptance (nếu có) được quản lý theo quy trình riêng;
không tự hiểu Released = Contract Accepted.
~~~

Không nhất thiết mọi nhóm phải có đủ các cột trên. Cần chọn **ranh giới phù hợp cách đo** và các bước ra quyết định thật.

### 18.2. Bốn flow metrics và một phép đo chờ riêng

| Chỉ số | Mô tả | Khi sai lầm Review gate xuất hiện |
| --- | --- | --- |
| **WIP** | Item đã bắt đầu nhưng chưa Done trong workflow | Có thể tăng vì item nằm chờ review cuối kỳ |
| **Work Item Age** | Tuổi của item đang WIP | Item chờ lâu hiện rõ trước khi Done |
| **Cycle Time** | Từ bắt đầu tới Done theo ranh giới đã định | Bị méo nếu “Done” đổi nghĩa từ đạt DoD sang có chữ ký |
| **Throughput** | Số item Done trong kỳ | Bị dồn thành đợt mỗi khi kết thúc Sprint nếu duyệt tập trung |
| **Done-to-release wait** | Thời gian từ đạt DoD tới release | Tách chờ phát hành khỏi thời gian phát triển |

**Định nghĩa phải ổn định.** Nếu trước đó ghi Done sau release và giờ ghi Done theo DoD, không so trực tiếp Cycle Time/throughput hai giai đoạn mà không công bố thay đổi.

### 18.3. Một ví dụ nhỏ về nhịp phê duyệt

Giả sử 8 Increment đủ điều kiện release tại các ngày làm việc khác nhau nhưng đều bị giữ tới cuộc Review cuối hai tuần. Mỗi Increment phải chờ thêm:

~~~text
1, 2, 3, 4, 5, 6, 7, 8 ngày làm việc
~~~

Thời gian chờ trung bình:

\[
\frac{1+2+3+4+5+6+7+8}{8}=\frac{36}{8}=4{,}5\ \text{ngày}
\]

Trung vị cũng là \((4+5)/2=4{,}5\) ngày. Đây là **ví dụ giả định để hiểu queue**, không phải đo thực của một Scrum Team.

Nếu release policy không bắt buộc chờ Review, nhóm có thể thảo luận bỏ cổng giữ này. Nếu cần gate chính thức, hãy đo thời gian chờ, chuẩn bị bằng chứng sớm và cải tiến phần được phép.

### 18.4. Không tạo hiệu suất giả bằng cách đổi nhãn

Nếu đang có 5 PBI chưa đạt DoD ở cột “Chờ khách hàng”, chuyển cả 5 sang “Done” để giảm WIP không làm phần mềm an toàn hơn. Hãy xem **điều kiện nào thực sự thiếu**. Ngược lại, nếu cả 5 đã đạt DoD và chỉ chờ hợp đồng, đừng giữ nhãn “Development” khiến dữ liệu phát triển không phản ánh sự thật.

## 19. XP và CI: chất lượng không nên đợi một buổi họp

Một cách tránh biến Review thành cổng nghiệm thu chất lượng là **xây khả năng kiểm chứng liên tục trong công việc**. Những thực hành kỹ thuật liên quan tới XP và agile engineering hỗ trợ điều này.

| Thực hành | Tác dụng | Không được diễn giải quá mức |
| --- | --- | --- |
| **TDD** | Làm rõ hành vi bằng test trước/đồng thời phát triển | Unit test không thay mọi kiểm tra ranh giới |
| **Continuous Integration** | Phát hiện xung đột sớm, giảm tích hợp muộn | Pipeline xanh không tự chứng minh người dùng đạt giá trị |
| **Pair programming/review** | Chia sẻ hiểu biết, phát hiện giả định sai | Không thay phê duyệt security bắt buộc |
| **Refactoring** | Giảm chi phí đổi hướng, giữ hành vi đã kiểm chứng | Không tự thay nghĩa vụ nghiệp vụ đã ký |
| **Small releases** | Có cơ hội giao giá trị và học sớm | Không miễn DoD hoặc điều kiện rollout |
| **Contract/integration tests** | Kiểm tra UI/API/DB và hệ thống phụ thuộc | Mock không chứng minh dịch vụ thật luôn đúng |

### 19.1. Test phải phản ánh rủi ro thật

Ví dụ một lỗi đăng ký trùng phát sinh bởi hai request concurrent. Một test với **một request tuần tự** không chứng minh hệ thống tránh được race condition. Cần kiểm chứng tầng ranh giới thích hợp, có dữ liệu giả và khả năng tái hiện.

### 19.2. CI thất bại giữa Sprint phải được xử lý ngay

Nếu build chung đỏ, việc chờ tới Sprint Review mới hỏi stakeholder có nghiệm thu không chỉ trì hoãn phát hiện. Developers cần điều tra, sửa hoặc hoàn nguyên theo chính sách, rồi xác minh chất lượng. **Không xóa test khó chỉ để demo xanh**.

### 19.3. Thay đổi nhỏ giảm độ lớn của phản hồi

PR nhỏ và tích hợp thường xuyên giúp reviewer và các test nhìn phạm vi thay đổi hẹp hơn. Khi phát hiện sai hợp đồng API, nhóm có thể sửa ở thời điểm còn ít phần phụ thuộc, thay vì tranh luận trong một buổi Review cuối kỳ.

## 20. Sử dụng Review để học về outcome, không chỉ chứng minh output

Phần mềm có thể được giao đúng yêu cầu nhưng người học vẫn không hoàn tất hành trình. Ví dụ:

- 100 người xem trang chi tiết khóa.
- 60 người bắt đầu thao tác đăng ký.
- 54 người đăng ký hợp lệ.
- Chỉ 21 người mở bài đầu trong vòng 7 ngày.

Đây là **dữ liệu giả định**, cần định nghĩa cohort và nguồn sự kiện trước khi dùng thực tế.

Tỷ lệ mở bài trong nhóm đã đăng ký:

\[
\frac{21}{54}\times100\%\approx38{,}9\%
\]

Số này có thể khiến Scrum Team đặt câu hỏi: người học không thấy nút mở bài, không có thời gian học hay nội dung không phù hợp?

**Chưa thể khẳng định nguyên nhân từ tỷ lệ.** Cần nghiên cứu, phân nhóm và phân tích sự kiện. Nhưng đây chính là kiểu thông tin tạo giá trị cho Sprint Review: giúp điều chỉnh giả định về Product Goal và ưu tiên Product Backlog.

### 20.1. Ba lớp tín hiệu nên đọc cùng nhau

| Lớp | Ví dụ chỉ số | Quyết định hỗ trợ |
| --- | --- | --- |
| **Delivery** | PBI Done, throughput, Cycle Time, Work Item Age | Luồng có đủ ổn định để giao? |
| **Quality** | Defect, contract tests, permission failures, incident | Tốc độ có làm xấu chất lượng? |
| **Outcome** | Task success, activation, thời gian mở bài, phản hồi | Người dùng đã thực sự nhận giá trị? |

Nếu chỉ đo delivery, Scrum Team có thể triển khai rất nhanh một hành trình ít ai sử dụng. Nếu chỉ xem outcome mà không biết chất lượng/dòng việc, khó chẩn đoán vấn đề.

### 20.2. Review dựa trên dữ liệu không có nghĩa giám sát người dùng vô hạn

Khi theo dõi hành vi học tập, cần định nghĩa dữ liệu tối thiểu, quyền truy cập, cách lưu và cách tổng hợp. Không nên thu thông tin nhạy cảm hơn mức cần thiết chỉ để có biểu đồ trình bày tại Review.

### 20.3. Chất lượng feedback quan trọng hơn số người dự họp

Một đại diện có hiểu biết về hành trình người học, một Increment đúng phiên bản và vài quan sát cụ thể có thể hữu ích hơn nhiều người chỉ xem slide rồi bấm “Approved”. Kết hợp định tính và định lượng để hiểu **vì sao** người học hành động như vậy.

## 21. Học từ phản hồi âm: không “rollback” trạng thái Done bằng cảm tính

Một stakeholder xem Increment đăng ký đã đạt DoD và nói:

> “Tôi không thích vị trí nút này. Vậy Sprint này chưa Done.”

Cần phân biệt:

1. **Nếu vị trí nút vi phạm tiêu chí chấp nhận/DoD đã xác định**, phải xem lại bằng chứng chất lượng; trạng thái Done trước đó có thể đã bị báo sai.
2. **Nếu đây là phát hiện mới về usability**, có thể tạo/điều chỉnh PBI theo thứ tự ưu tiên; phát hiện mới **không tự xóa** thực tế rằng Increment đã đạt DoD theo chuẩn hiện hành.
3. **Nếu phản hồi phản ánh rủi ro an toàn hoặc yêu cầu pháp lý bắt buộc**, cần xử lý theo trách nhiệm tương ứng; không dựa vào cách phân loại “chỉ là ý kiến” để bỏ qua.
4. **Nếu đó là thay đổi đầu ra hợp đồng**, cần xác minh baseline và quyền phê duyệt.

### 21.1. Tại sao “sửa Done về In Progress” có thể gây hại?

Nếu mỗi ý tưởng mới đều xóa trạng thái Done:

- Throughput không còn phản ánh những Increment đã hoàn tất thật.
- Developers thiếu thông tin ổn định về chuẩn chất lượng.
- Dự báo dựa trên dữ liệu Done trở nên thiếu tin cậy.
- Khách hàng không phân biệt defect với học hỏi mới.

Nhưng chiều ngược lại cũng nguy hiểm: **không dùng DoD cũ như lá chắn để không sửa lỗi thật**. Khi phát hiện tiêu chuẩn thiếu hoặc sản phẩm có khiếm khuyết, cần xử lý theo mức độ và cập nhật cách kiểm chứng phù hợp.

### 21.2. Ví dụ diễn đạt sau Review

> “Lát cắt đăng ký đã đáp ứng DoD hiện hành. Trong buổi Review, chúng ta phát hiện người học khó tìm nút mở bài; đây là phản hồi về trải nghiệm cần được Product Owner xem xét trong Product Backlog. Nhóm cũng sẽ kiểm tra xem vấn đề có làm sai tiêu chí sử dụng đã thống nhất không. Không coi ý kiến mới là thủ tục nghiệm thu lại toàn bộ Sprint.”

## 22. Nguyên tắc tổ chức khi có hai loại “acceptance”

Từ “acceptance” trong tiếng Anh có thể chỉ **xác nhận hành vi PBI** hoặc **nghiệm thu hợp đồng**. Trong nhiều dự án, chính một từ này làm các nhóm tưởng rằng mọi thứ phải chờ Sprint Review.

### 22.1. Cách đặt tên trạng thái rõ hơn

| Tên trạng thái | Ý nghĩa nên nêu rõ |
| --- | --- |
| **Acceptance criteria verified** | Hành vi PBI đã được kiểm tra theo ví dụ hiện tại |
| **Done (DoD)** | Increment đạt toàn bộ chuẩn chất lượng đã xác định |
| **Ready for release** | Đáp ứng điều kiện trước rollout theo chính sách |
| **Released** | Đã triển khai/giao cho đối tượng được phép |
| **Contract accepted** | Đã có quyết định nghiệm thu hợp đồng theo thẩm quyền |
| **Outcome observed** | Có dữ liệu sử dụng/đánh giá về kết quả người dùng |

Không cần bắt buộc mọi hệ thống ticket dùng đúng sáu nhãn. Chọn cách biểu diễn **trung thực và nhất quán** để không nhầm “PO Accepted” thành “đã được ký nghiệm thu hợp đồng”.

### 22.2. Khi khách hàng chỉ cho phép nghiệm thu vào cuối đợt

Một hợp đồng có thể quy định nghiệm thu cuối kỳ. Scrum Team vẫn có thể **xây Increment Done và thu phản hồi sớm** trong môi trường được phép. Nếu chính sách không cho phát hành trước nghiệm thu, hãy **quản lý release gate độc lập và đưa rủi ro chờ đợi vào kế hoạch**.

Trong trường hợp đó, không nên hứa người dùng production sẽ nhận phần mềm vào giữa Sprint nếu chưa đủ điều kiện. Nhưng cũng không nên đánh đồng **“chưa được phép release”** với **“Scrum Team không được học hỏi”**.

### 22.3. Những văn bản cần truy vết khi hợp đồng cứng

Có thể có SOW, acceptance plan, quy tắc dữ liệu, release policy, change-control procedure và người ký theo ủy quyền. Nhóm nên xác minh **bộ tài liệu thực sự áp dụng** với bên có quyền, không suy đoán rằng một biên bản cuộc họp đủ thay thế tất cả.

## 23. Khi một Sprint Review thất bại: cải tiến hệ thống thay vì tìm người để trách

“Review thất bại” đôi khi là cách gọi chủ quan. Một buổi Review có nhiều phản hồi khó nghe **không đồng nghĩa Sprint đã thất bại**; đó có thể là tín hiệu rất giá trị về giả định sản phẩm.

Tuy nhiên, nếu vấn đề lặp lại như “cứ tới Review mới phát hiện hành vi sai”, nhóm cần điều tra:

- Người dùng và PO có cơ hội trao đổi ví dụ nghiệp vụ trước khi xây không?
- Developers có thử một lát cắt nhỏ trước khi thiết kế toàn bộ luồng?
- Test chỉ kiểm tra happy path hay có timeout, retry và phân quyền?
- DoD có đủ tiêu chuẩn rủi ro quan trọng?
- CI có đáng tin hay thường phải rerun để xanh?
- Hợp đồng/ủy quyền có tạo hàng chờ làm rõ lâu không?
- Stakeholders có tham gia phản hồi thường xuyên được không?
- Nhóm có sợ trình bày rủi ro sớm vì bị trừng phạt hoặc đánh giá không?

### 23.1. Phân tích nguyên nhân không đổ lỗi

**Vấn đề minh họa:** Ba Sprint liên tiếp phát hiện sai trạng thái đăng ký chỉ vào Review.

| Câu hỏi “vì sao” | Giả thuyết cần kiểm chứng |
| --- | --- |
| Vì sao phát hiện muộn? | Không có thử hành vi với người dùng trong Sprint |
| Vì sao không thử trước? | Nhóm nghĩ chỉ Review mới được xem Increment |
| Vì sao có chính sách ấy? | Nhầm Sprint Review với nghiệm thu hợp đồng |
| Vì sao nhầm vẫn tồn tại? | Quyền và loại bằng chứng chưa được làm rõ |
| Vì sao không được làm rõ? | Không có trao đổi giữa PO, contract manager và Developers về ranh giới |

Đây là **chuỗi giả thuyết minh họa**, không phải kết luận khi chưa có dữ liệu. 5 Whys nên mở nhiều nhánh nếu có yếu tố kỹ thuật, nghiệp vụ và tổ chức cùng góp phần.

### 23.2. Một cải tiến có thể thử

Trong hai Sprint:

1. Chọn một lát cắt có rủi ro sử dụng cao.
2. Dùng acceptance examples và contract tests trước khi tích hợp lớn.
3. Khi Increment đạt DoD, cho người dùng được phép preview sớm.
4. Theo dõi thời gian Done-to-feedback, Done-to-release và lỗi phát hiện muộn.
5. Giữ Sprint Review để trao đổi Product Goal, feedback và Product Backlog.
6. Giữ gate hợp đồng/an toàn thật ở vị trí riêng với người quyết định rõ.

**Đánh giá sau thử:** Nếu phản hồi đến sớm hơn nhưng lỗi production hoặc vi phạm quyền tăng, không được xem là cải tiến thành công. Cần đọc cùng guardrails chất lượng và an toàn.

### 23.3. Cải tiến không chờ tới Retrospective nếu có nguy cơ ngay

**Sprint Retrospective** là nơi Scrum Team xem cách nâng cao chất lượng và hiệu quả, nhưng một lỗi dữ liệu đang ảnh hưởng người dùng cần ứng cứu ngay. Review cũng không phải nơi duy nhất được phép nhận phản hồi an toàn.

## 24. Case study xuyên suốt: đăng ký khóa học nhưng người học không mở được bài

### 24.1. Bối cảnh

Một Scrum Team phát triển nền tảng học trực tuyến, dùng Sprint dài hai tuần. Product Goal của giai đoạn này:

> “Người học mới có thể đăng ký một khóa miễn phí và bắt đầu bài đầu tiên thuận lợi, an toàn.”

Nhóm có các PBI:

| PBI | Hành vi người dùng | Tiêu chí chất lượng quan trọng |
| --- | --- | --- |
| **A — Đăng ký miễn phí** | Lưu đăng ký hợp lệ, xác nhận đúng trạng thái | Không tạo đăng ký Active trùng, xử lý timeout |
| **B — Xem khóa đã đăng ký** | Xem danh sách theo tài khoản | Không lộ khóa của người khác |
| **C — Mở bài đầu** | Truy cập nội dung sau đăng ký | Quyền học hợp lệ, kết quả UI/API nhất quán |
| **D — Tiến độ học** | Lưu và khôi phục tiến độ | Không ghi đè âm thầm, kiểm thử tích hợp |

Một stakeholder đề xuất chính sách:

> “Chỉ được đánh dấu PBI Done sau khi tôi duyệt tất cả tại Sprint Review. Trước Review, chưa ai được xem phần mềm và không được phát hành.”

Vấn đề không chỉ là một cuộc họp. Chính sách ấy biến **điểm học hỏi** thành **điểm nghẽn duy nhất**.

### 24.2. Điều gì xảy ra theo dòng thời gian?

| Thời điểm giả định | Sự kiện | Kết quả nếu giữ cổng Review |
| --- | --- | --- |
| **Ngày 1** | Sprint Planning: mục tiêu đăng ký và mở bài | Kế hoạch có giá trị nhưng chưa rõ retry |
| **Ngày 3** | API đăng ký và UI có lát cắt chạy được | Không được người dùng thử |
| **Ngày 4** | A đạt DoD theo bằng chứng hiện có | Vẫn bị giữ trạng thái In Progress chờ chữ ký |
| **Ngày 5** | Một Developer phát hiện timeout hiển thị mơ hồ | Muốn làm rõ nghiệp vụ nhưng được bảo “đợi Review” |
| **Ngày 7** | B đạt DoD, C còn phụ thuộc API quyền | Không có phản hồi về hành trình tổng thể |
| **Ngày 9** | Review chuẩn bị, nhiều item chờ báo cáo | Hàng chờ và áp lực cuối kỳ tăng |
| **Ngày 10** | Stakeholder nhận ra người học khó tìm nút mở bài | Phản hồi tới muộn, các giả định đã lan sang D |

Số ngày và tình huống đều **giả định cho bài học**. Nếu có yêu cầu an toàn giới hạn quyền preview, nhóm phải chọn người được phép và dữ liệu an toàn, không bỏ kiểm soát.

### 24.3. Phân tích bốn điểm sai

**Điểm sai 1 — Trạng thái Done bị xác định bởi lịch họp:** A đã đạt DoD nhưng vẫn bị đặt In Progress, khiến dữ liệu Cycle Time và throughput méo.

**Điểm sai 2 — Không cho phản hồi trước Review:** Người học không có cơ hội làm rõ hành vi khi sửa còn rẻ.

**Điểm sai 3 — Coi mọi góp ý thành điều kiện nghiệm thu:** Yêu cầu “thêm email xác nhận” có thể là nhu cầu mới, không tự là defect của A.

**Điểm sai 4 — Tưởng Review sẽ thay kiểm thử:** Nếu C còn sai quyền truy cập, không thể được “ký cho qua”.

### 24.4. Tổ chức lại mà không thay Scrum

Nhóm và stakeholder thống nhất:

1. **DoD xác định Done** bằng bằng chứng chất lượng, không phải lịch của một buổi Review.
2. **Developers, PO và người dùng được phép** trao đổi ví dụ và thử lát cắt ngay trong Sprint.
3. Những Increment Done **có thể giao sớm** nếu release policy được đáp ứng; không cần chờ Review.
4. Review cuối Sprint **kiểm tra kết quả và những điều học được**, không xin ký lại từng task.
5. Phát hiện mới được phân loại thành lỗi, làm rõ, cải tiến hoặc thay đổi nghĩa vụ.
6. Nghiệm thu hợp đồng (nếu có) dùng **bằng chứng và thẩm quyền riêng**.
7. Sau Review, nhóm dùng feedback để làm rõ Product Backlog, không tự gọi mọi đề nghị là commitment trong Sprint tiếp theo.

### 24.5. Một kịch bản Gherkin kiểm chứng giá trị

~~~gherkin
Tính năng: Người học đăng ký và bắt đầu khóa miễn phí

  Tình huống: Đăng ký hợp lệ và mở bài đầu
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" cho phép đăng ký miễn phí
    Và người học chưa có đăng ký đang có hiệu lực
    Khi người học đăng ký khóa
    Thì hệ thống lưu đăng ký hợp lệ
    Và giao diện hiển thị đúng trạng thái đã đăng ký
    Và người học có thể mở bài đầu tiên theo quyền hợp lệ

  Tình huống: Hai yêu cầu gần đồng thời
    Cho trước người học chưa có đăng ký Active của khóa
    Khi hai yêu cầu đăng ký được gửi gần đồng thời
    Thì hệ thống không tạo hai đăng ký Active trùng nhau
    Và phản hồi của mỗi yêu cầu tuân hợp đồng đã thống nhất

  Tình huống: Kết quả lưu chưa chắc chắn sau timeout
    Cho trước phản hồi đăng ký chưa tới client
    Khi người học kiểm tra trạng thái của thao tác vừa gửi
    Thì giao diện không báo chắc chắn thành công nếu chưa được xác minh
    Và người học có thể xác định trạng thái hoặc thử lại an toàn

  Tình huống: Phân quyền tài khoản
    Cho trước tài khoản A đã đăng nhập
    Và đăng ký thuộc tài khoản B
    Khi A cố truy cập đăng ký của B
    Thì hệ thống từ chối theo chính sách phân quyền
    Và không tiết lộ dữ liệu riêng của B
~~~

Gherkin chỉ mô tả hành vi mong muốn. Kiểm thử đồng thời thật sự cần runner, dữ liệu thử và ranh giới DB/dịch vụ đại diện. **Một kịch bản Gherkin được viết chưa chứng minh đã đạt DoD**.

### 24.6. Một Sprint Review sau khi đã cải tiến

Thay vì để stakeholder duyệt task A, B, C, nhóm trình bày:

> “Người học hiện có thể đăng ký và xem khóa đã đăng ký theo quyền. Các lát cắt A và B đã đạt DoD và được thử trên môi trường phù hợp. Lát cắt C chưa đạt DoD vì quyền mở bài còn lỗi trong trường hợp hủy đăng ký, nên không được giới thiệu như Increment Done. Từ thử nghiệm sử dụng, chúng tôi thấy xác nhận đăng ký đã rõ hơn nhưng đường dẫn mở bài còn khó tìm. Chúng ta sẽ thảo luận thứ tự Product Backlog để cải thiện hành trình này, đồng thời tiếp tục xử lý rủi ro phân quyền.”

Đây là một Review **minh bạch chất lượng và phục vụ quyết định sản phẩm**, không phải “đội đạt 75% điểm và xin duyệt 3/4 stories”.

### 24.7. Kiểm tra hiệu quả sau thay đổi

Nhóm nên xem:

- Thời gian từ **DoD tới phản hồi đầu tiên** có giảm không?
- Thời gian từ **DoD tới release** có giảm trong những trường hợp đủ điều kiện không?
- Work Item Age và blocked time của các PBI còn dở có giảm?
- Lỗi phân quyền, retry hoặc dữ liệu có tăng/giảm?
- Người học thực sự bắt đầu bài đầu có tăng theo cách đo nhất quán?
- Review có đưa ra những hiểu biết và quyết định backlog tốt hơn không?

**Không cần một chỉ số duy nhất cho “Review tốt”.** Một thay đổi giảm chờ nhưng làm tăng lỗi dữ liệu không thể gọi là thành công.

## 25. Tình huống đối lập: khi việc chờ nghiệm thu là nghĩa vụ thật

Một đơn vị đào tạo khác thuê nhà cung cấp theo hợp đồng có điều kiện: **không được mở dữ liệu người học thật trước khi bên mua hoàn tất một thủ tục nghiệm thu an toàn**, và chỉ người được ủy quyền mới có thể ký.

Nhóm phát triển vẫn dùng Scrum với Sprint hai tuần, nhưng việc release production còn gate bắt buộc.

### 25.1. Những gì nhóm không nên làm

- Không tự nói “Scrum cấm gate nên cứ cho người học thật truy cập”.
- Không bỏ kiểm tra quyền dữ liệu hoặc an toàn để đẩy nhanh feedback.
- Không tự dùng dữ liệu thật ở môi trường preview trái quyền.
- Không lấy sự đồng ý của một người dự Sprint Review thay chữ ký hợp đồng.
- Không tự đánh dấu “contract accepted” chỉ vì Increment đạt DoD.

### 25.2. Những gì nhóm vẫn có thể làm

1. Chia nhu cầu thành các PBI có hành vi thật và tiêu chí rõ.
2. Tích hợp, kiểm thử và đạt DoD liên tục trong môi trường cho phép.
3. Nhận phản hồi từ **người dùng được phép với dữ liệu giả/đã được xử lý theo chính sách**.
4. Duy trì Sprint Review để inspect & adapt.
5. Chuẩn bị bằng chứng nghiệm thu và release gate ngay từ lúc phát triển.
6. Theo dõi **hàng chờ nghiệm thu** và người có quyền, không gọi đó là lỗi của Developers.
7. Chỉ release khi điều kiện có hiệu lực được đáp ứng.

### 25.3. Cách báo cáo không nhập nhằng

> “Lát cắt đăng ký đã đạt DoD và có thể sử dụng trong môi trường thử được phép. Release production hiện chưa được phê duyệt vì còn thủ tục nghiệm thu an toàn theo hợp đồng. Sprint Review tuần này vẫn diễn ra để kiểm tra kết quả, thu phản hồi trên dữ liệu an toàn và làm rõ Product Backlog; quyết định hợp đồng sẽ do chủ thể có quyền thực hiện theo thủ tục riêng.”

### 25.4. Câu hỏi quan trọng

**Chờ nghiệm thu có luôn là sai?** Không. Sai lầm của bài này là **biến Sprint Review thành cổng nghiệm thu duy nhất bất kể bản chất công việc và quyền**, không phải phản đối một gate hợp lệ. Cần nhận diện **cái gì thực sự phải chờ**, rồi cải thiện những phần không bắt buộc phải chờ.

## 26. Bài tập A: phân biệt Done, release, Review và nghiệm thu

Với mỗi tình huống, xác định: **PBI/Increment có Done không? Có thể release không? Sprint Review nên làm gì? Có cần nghiệm thu chính thức không?**

### Tình huống

| Mã | Dữ kiện |
| --- | --- |
| **A** | Luồng đăng ký đạt DoD, release policy đã đạt; Sprint Review còn ba ngày mới diễn ra |
| **B** | UI mock chạy, nhưng test quyền dữ liệu và tích hợp chưa đạt |
| **C** | Increment đạt DoD, nhưng gate bảo mật production chưa phê duyệt |
| **D** | Stakeholder tại Review muốn có dashboard mới ngoài tiêu chí hiện tại |
| **E** | Product Owner nói “accept” PBI, nhưng test chống đăng ký trùng thất bại |
| **F** | Hợp đồng đòi người có thẩm quyền ký nghiệm thu theo giai đoạn; buổi Review vừa được tổ chức |
| **G** | Increment đã release an toàn trước ngày Review và dữ liệu sử dụng cho thấy activation thấp |
| **H** | Một PBI chưa đạt DoD, nhưng các Developers muốn demo như kết quả chính của Sprint |

### Câu hỏi bổ sung

1. Vì sao trong tình huống A không phải đợi Review mới được giao?
2. Trong C và F, điều gì vẫn có thể được học trước khi có quyết định hợp đồng/release?
3. Tình huống D là lỗi chất lượng hay phản hồi sản phẩm mới?
4. Tình huống G cho thấy Sprint Review còn cần thiết không?
5. Trong E, ai có trách nhiệm đưa PBI tới DoD?

### Gợi ý lời giải

| Mã | Cách xử lý phù hợp |
| --- | --- |
| **A** | **Done**, có thể release theo chính sách trước Review; Review vẫn kiểm tra kết quả và hướng tương lai |
| **B** | **Chưa Done**; mock không thay Increment tích hợp; cần tiếp tục hoàn thiện và kiểm thử |
| **C** | **Done nhưng chưa được release**; xử lý gate theo quyền, không nhập nó vào Sprint Review |
| **D** | Ghi phản hồi, kiểm tra giá trị và phạm vi; có thể điều chỉnh Product Backlog hoặc gửi change request nếu cần |
| **E** | **Chưa Done** vì test rủi ro bắt buộc chưa đạt; lời PO không thay bằng chứng DoD |
| **F** | Review Scrum không tự là nghiệm thu hợp đồng; cần quy trình/đúng người ký |
| **G** | Review vẫn cần để kiểm tra outcome, thảo luận activation thấp và thích ứng Product Backlog |
| **H** | Không giới thiệu PBI đó tại Review như Increment Done; cần minh bạch tình trạng và xem lại Product Backlog |

**Câu 1:** Scrum cho phép Increment được giao trước cuối Sprint và không xem Sprint Review là cổng release. Nếu release policy thực tế đã đáp ứng, không có lý do Scrum bắt buộc chờ.

**Câu 2:** Có thể thử trên môi trường được phép, dùng dữ liệu an toàn, làm rõ hành vi, xem Increment đã đạt DoD và thu phản hồi; không tự phê duyệt phần bị ràng buộc.

**Câu 3:** Chưa đủ dữ kiện để gọi lỗi. Nếu dashboard không là tiêu chí hiện tại, có thể là cơ hội mới hoặc thay đổi hợp đồng; cần phân loại.

**Câu 4:** Có. Review không phải buổi “lần đầu được thấy phần mềm” mà là lúc cùng xem **kết quả và thông tin mới** để quyết định hướng sản phẩm.

**Câu 5:** Developers chịu trách nhiệm tạo Increment đáp ứng DoD; PO cộng tác làm rõ giá trị/tiêu chí và quản lý Product Backlog.

## 27. Bài tập B: tính thời gian bị giữ ở cổng Review

Một nhóm có 8 Increment hoặc lát cắt đã đạt DoD, đủ điều kiện được giao theo chính sách, nhưng vì **quy định nội bộ chưa có căn cứ rõ rằng phải đợi Sprint Review**, mỗi phần phải chờ thêm số ngày làm việc sau DoD:

~~~text
1, 2, 3, 4, 5, 6, 7, 8
~~~

Giả sử 8 phần **độc lập và không chồng lắp trong phép cộng thời gian chờ trên từng item**. Đây là dữ liệu giả định.

### Câu hỏi

1. Tính tổng số **ngày-item chờ**.
2. Tính trung bình và trung vị **Done-to-release wait**.
3. Có thể kết luận đó là 36 ngày công nhân sự bị lãng phí không?
4. Nếu bỏ cổng này và mọi phần được giao ngay sau DoD khi đủ điều kiện, thành phần thời gian chờ do cổng này còn bao nhiêu?
5. Nếu Cycle Time trước đây được định nghĩa từ bắt đầu tới **DoD**, có được cộng thời gian chờ release vào để nói Cycle Time đã tăng không?
6. Nếu release gate an toàn bắt buộc vẫn còn, nhóm cần đo riêng điều gì?
7. Nêu hai guardrails khi thử giao sớm hơn.
8. Vì sao chỉ nhìn số Increment được giao cuối Sprint có thể che vấn đề?

### Lời giải

**Câu 1:**

\[
1+2+3+4+5+6+7+8=36\ \text{ngày-item chờ}
\]

Đây là **tổng thời gian chờ tính theo từng item**, không là 36 ngày trên lịch dự án và không tương đương 36 ngày công nhân sự.

**Câu 2:**

\[
\text{Trung bình}=\frac{36}{8}=4{,}5\ \text{ngày/item}
\]

Trung vị \(=(4+5)/2=4{,}5\) ngày.

**Câu 3:** Không. Trong lúc một Increment chờ release, Developers có thể đang thực hiện PBI khác; thời gian chờ của item **khác** thời gian một nhân viên không làm việc.

**Câu 4:** Nếu **chỉ riêng cổng giả tạo** gây ra phần chờ này và mọi điều kiện release khác đã được đáp ứng, thời gian chờ do cổng ấy về lý tưởng có thể giảm tới **0**. Không khẳng định tổng thời gian tới người dùng luôn bằng 0 vì còn triển khai, lịch vận hành hoặc phụ thuộc khác.

**Câu 5:** Không, nếu cách đo Cycle Time vẫn dừng tại DoD. Phải báo **Done-to-release wait** hoặc lead time tới sử dụng riêng; muốn đổi workflow metric phải công bố định nghĩa và cẩn trọng khi so sánh lịch sử.

**Câu 6:** Đo thời gian chuẩn bị bằng chứng, chờ quyết định có quyền, thời gian thực hiện rollout và nguyên nhân bị từ chối nếu có.

**Câu 7:** Số lỗi nghiêm trọng sau phát hành, dữ liệu/phân quyền, tỷ lệ rollback, tính tin cậy của CI, khả năng phát hiện/khôi phục và điều kiện DoD; chọn guardrail theo rủi ro.

**Câu 8:** Nếu tất cả phần mềm bị giữ tới một ngày, biểu đồ delivery có thể thấy tăng đột biến vào cuối Sprint dù Increment đã sẵn trước đó. Cần tách **thời điểm Done** và **thời điểm giao**.

## 28. Bài tập C: thiết kế một Sprint Review có ích cho Product Goal

Scrum Team có Sprint Goal:

> “Người học đăng ký khóa miễn phí và mở được bài đầu với trạng thái đáng tin.”

Cuối Sprint:

- PBI A đăng ký đã đạt DoD và được release theo quy trình.
- PBI B danh sách khóa đã đăng ký đạt DoD nhưng chưa release vì lịch rollout.
- PBI C mở bài đầu chưa đạt test phân quyền và do đó chưa Done.
- User research của nhóm A cho thấy nhiều người không biết mở bài ở đâu.
- Sponsor đề nghị thêm chứng chỉ điện tử vào sản phẩm.
- Một khách hàng hợp đồng muốn ký nghiệm thu theo mẫu vào tuần sau.

### Yêu cầu

1. Viết **mục đích của Sprint Review** trong một câu.
2. Đề xuất một agenda khoảng 45–60 phút.
3. Xác định nội dung nào có thể giới thiệu như **Increment Done**.
4. Có nên trình bày PBI C như một phần Increment hoàn thành không?
5. Phản hồi nghiên cứu và yêu cầu chứng chỉ được xử lý thế nào?
6. Buổi Review có nên ký nghiệm thu hợp đồng ngay không?
7. Viết ba câu hỏi giúp stakeholders bàn về **Product Goal**, không chỉ sở thích giao diện.
8. Viết đoạn kết luận Review gồm thông tin mới, việc cần xem xét và quyền quyết định.

### Gợi ý lời giải

**Câu 1:** Sprint Review giúp Scrum Team và stakeholders **kiểm tra kết quả Sprint, tiến bộ hướng Product Goal và thích ứng kế hoạch sản phẩm**.

**Câu 2:** 5 phút bối cảnh/Product Goal; 10 phút kết quả Sprint Goal và Increment; 15 phút dùng thử A/B cùng phản hồi; 10 phút nghiên cứu và rủi ro từ C; 10 phút lựa chọn Product Backlog; 5 phút tóm tắt người cần quyết định.

**Câu 3:** A và B đã đạt DoD; B chưa release nhưng vẫn Done theo Scrum. C không được giới thiệu như Increment Done.

**Câu 4:** Không. Có thể minh bạch rủi ro và việc chưa hoàn tất, nhưng không xem PBI C là phần Increment để yêu cầu stakeholders “accept” thay cho kiểm thử phân quyền.

**Câu 5:** Người dùng khó mở bài là vấn đề outcome/UX cần kiểm chứng; PO cân nhắc Product Backlog. Chứng chỉ điện tử có thể là nhu cầu mới, cần làm rõ giá trị/phạm vi và thủ tục thay đổi hợp đồng nếu tác động nghĩa vụ.

**Câu 6:** Không mặc định. Nếu hợp đồng đòi mẫu và người có quyền ký, phải thực hiện theo quy trình riêng, có thể dùng một phần bằng chứng từ Increment đã Done.

**Câu 7:** Ví dụ:

- Người học sau khi đăng ký có thể tự tìm và mở bài đầu trong điều kiện thực tế không?
- Những tình huống chưa rõ trạng thái hoặc quyền làm giảm sự tin cậy?
- Nếu chỉ cải thiện một phần của hành trình trong Sprint tới, điều gì có khả năng tạo giá trị lớn nhất?

**Câu 8 — Đoạn kết minh họa:**

> “Chúng ta đã có Increment đăng ký và danh sách khóa đạt DoD; đăng ký đã phát hành, còn danh sách khóa chờ lịch rollout theo chính sách. Luồng mở bài đầu chưa đạt DoD vì lỗi phân quyền. Phản hồi người học cho thấy cần ưu tiên làm rõ đường tới bài đầu; Product Owner sẽ cùng Developers phân tích và sắp thứ tự trong Product Backlog. Đề nghị chứng chỉ điện tử cần xác minh giá trị, phạm vi và quyền phê duyệt. Thủ tục nghiệm thu hợp đồng được xử lý ở mốc riêng theo người có thẩm quyền. Sprint Review không quyết định thay các gate đó.”

## 29. Bài tập D: khi “được ký” nhưng vẫn còn lỗi dữ liệu

Một nhóm có một hệ thống đăng ký khóa. Trong buổi Sprint Review:

- Demo với một yêu cầu đăng ký thành công.
- Product Owner nói “Accept”.
- Stakeholder đề nghị đưa hệ thống cho 2.000 người học dùng ngay.
- Nhưng Developers biết hai test quan trọng đang thất bại: **retry có thể tạo bản ghi Active trùng** và **tài khoản A xem được dữ liệu tài khoản B**.
- DoD của sản phẩm yêu cầu test an toàn dữ liệu và phân quyền đạt.
- Quy trình production còn yêu cầu release approval và phương án rollback.

### Câu hỏi

1. PBI có Done không? Giải thích từ DoD.
2. Product Owner đã nói “Accept” có làm đổi tình trạng không?
3. Có thể phát hành cho 2.000 người học ngay không?
4. Phải làm gì nếu phát hiện đã có dữ liệu của người dùng thật bị ảnh hưởng?
5. Cần kiểm thử lại ở những ranh giới nào?
6. Nếu có người nói “chỉ cần đặt feature flag ẩn chức năng”, điều gì vẫn cần xét?
7. Tại Review nên trình bày thế nào để không giấu vấn đề?
8. Sau khi sửa, bằng chứng nào cho phép gọi Done và xem xét release?

### Gợi ý lời giải

**Câu 1:** Không. Hai test bắt buộc chưa đạt nên PBI chưa đáp ứng DoD, không là Increment Done.

**Câu 2:** Không. PO chịu trách nhiệm giá trị và Product Backlog, không có quyền bằng một lời nói thay đổi thực tế kiểm chứng và chuẩn chất lượng áp dụng.

**Câu 3:** Không. Có nguy cơ dữ liệu và chưa đủ DoD/release gate; phải bảo vệ người học và xử lý đúng quyền trước.

**Câu 4:** Ứng cứu theo chính sách, ngăn tiếp tục gây hại, ghi nhận và bảo vệ bằng chứng phù hợp, phối hợp security/privacy/incident response theo quyền; không tự xóa dữ liệu production hoặc chờ Retrospective.

**Câu 5:** Kiểm thử tình huống đồng thời/retry ở API–DB, quyền truy cập theo danh tính trên API và giao diện, đồng thời kiểm tra hợp đồng và xử lý lỗi.

**Câu 6:** Flag phải có khả năng bảo vệ đúng đường thực thi và không che dữ liệu sai; code/Increment và điều kiện release vẫn cần đáp ứng. Không coi feature flag là giấy miễn test.

**Câu 7:** Công bố trung thực phần hành vi đã kiểm chứng và phần **chưa Done**, rủi ro, hành động khắc phục và việc cần phối hợp. Không giới thiệu phần chưa đạt DoD như kết quả hoàn tất.

**Câu 8:** Test hồi quy và tích hợp thực sự đạt, kiểm chứng tính nhất quán/phân quyền, review và chứng cứ DoD đầy đủ; sau đó release approval và điều kiện vận hành theo chính sách.

## 30. Ba mươi ngộ nhận khiến Sprint Review bị biến thành cổng nghiệm thu

**1. “Sprint Review chính là buổi khách hàng kiểm tra từng story để ký Done.”** Không. Mục đích của Review là kiểm tra kết quả Sprint và điều chỉnh tương lai. Done theo DoD, không theo cảm nhận từ một cuộc họp.

**2. “Increment chỉ có thể được giao sau Sprint Review.”** Sai. Scrum cho phép Increment được giao trước khi Sprint kết thúc và không xem Review là cổng phát hành giá trị.

**3. “Phần mềm đạt DoD thì bắt buộc phải deploy production ngay.”** Không. Release policy, dữ liệu và gate bắt buộc có thể áp dụng riêng; cần phân biệt Done với released.

**4. “Khách hàng không thích giao diện mới thì mọi PBI trong Sprint mất trạng thái Done.”** Phản hồi mới có thể tạo công việc mới; nếu vi phạm tiêu chí/DoD thì phải xử lý sai sót thật. Không đánh đồng hai trường hợp.

**5. “Product Owner là người duy nhất có quyền đóng dấu Done.”** Product Owner quản lý giá trị và Product Backlog; Increment Done theo Definition of Done do Developers bảo đảm.

**6. “Khách hàng ký đã đạt thì security test có thể chưa chạy.”** Không. Những kiểm tra bắt buộc không biến mất vì một buổi duyệt.

**7. “Để tới Review mới hỏi yêu cầu sẽ tiết kiệm cuộc họp.”** Có thể tiết kiệm giao tiếp trước mắt nhưng tăng làm lại và chờ đợi.

**8. “Cho người dùng thử giữa Sprint sẽ làm Review mất ý nghĩa.”** Ngược lại, dữ liệu sử dụng sớm giúp Review có thêm thông tin để quyết định Product Backlog.

**9. “Review chỉ cần demo happy path.”** Những luồng lỗi, quyền, dữ liệu và kết quả người dùng có thể quyết định giá trị và chất lượng.

**10. “Review thay hết kiểm thử tích hợp.”** Một demo không chứng minh tính đúng đắn của retry, race condition, migration hay phân quyền.

**11. “Story đã có acceptance criteria đạt thì chắc chắn Done.”** Còn phải đáp ứng toàn bộ Definition of Done áp dụng cho Increment.

**12. “Có DoD là đủ, không cần làm rõ hành vi của PBI.”** DoD là mức chất lượng chung; acceptance examples giúp hiểu hành vi cụ thể.

**13. “Sprint Review là nghiệm thu hợp đồng, nên tự động được thanh toán.”** Nghiệm thu và thanh toán theo điều khoản, bằng chứng và người có quyền.

**14. “Nếu hợp đồng bắt buộc nghiệm thu, Scrum không dùng được.”** Vẫn có thể tạo Increment Done và Review thường xuyên trong môi trường/quyền được phép; gate hợp đồng quản lý riêng.

**15. “Không có chữ ký nghiệm thu thì mọi thứ vẫn phải để In Progress.”** Hãy phân biệt trạng thái chất lượng sản phẩm với trạng thái hợp đồng.

**16. “Mọi feedback tại Review là một lỗi phải sửa miễn phí.”** Có thể là defect, làm rõ, ý tưởng mới hoặc thay đổi nghĩa vụ; cần phân loại.

**17. “Mọi feedback mới đều là scope creep.”** Có phản hồi chỉ ra sai sót so với tiêu chí đã cam kết hoặc giúp làm rõ hành vi.

**18. “PO nghe xong đã đồng ý thì được đổi hợp đồng.”** Quyền thay nghĩa vụ thuộc chủ thể được ủy quyền theo quy trình.

**19. “Sprint Goal đạt là hợp đồng đã hoàn thành.”** Sprint Goal là commitment của Sprint Backlog, không thay tiêu chí nghiệm thu.

**20. “Ba nhóm báo Done phần UI/API/DB thì luồng người dùng đã Done.”** Nếu chưa tích hợp thành Increment đạt DoD, chưa được gọi Done cho kết quả sản phẩm.

**21. “Nhiều nhóm phải có một Super Review mới được merge mã.”** Scrum không yêu cầu đợi buổi họp; cần CI, tích hợp và DoD chung khi cùng sản phẩm.

**22. “Scrum of Scrums là cấp duyệt Done giữa các nhóm.”** Đây là cơ chế phối hợp có thể chọn, không phải sự kiện/cổng nghiệm thu bắt buộc của Scrum.

**23. “Reviewer kỹ thuật và stakeholder nghiệp vụ là cùng một vai trò.”** Review mã/bảo mật và Sprint Review có mục đích, bằng chứng, thẩm quyền khác nhau.

**24. “Một cột Approved đẹp là bằng chứng quá trình giao hàng nhanh.”** Cần xem hàng chờ, Work Item Age, Cycle Time, Done-to-release wait và chất lượng.

**25. “Đổi nhãn In Progress thành Done sẽ giảm chờ.”** Số liệu đổi nhưng giá trị thực và điều kiện release không thay đổi.

**26. “Chỉ cần đo số Increment release mỗi Sprint.”** Có thể bỏ qua mức sử dụng, lỗi và thời gian chờ của các phần đã Done sớm.

**27. “Nếu người dùng chưa phàn nàn thì không có vấn đề.”** Có thể ít sử dụng, thiếu telemetry hoặc người dùng không có kênh phản hồi.

**28. “Một người nói ‘không thích’ là đủ để kết luận giải pháp sai.”** Cần xem bối cảnh, người dùng đại diện, tiêu chí và thêm bằng chứng; vẫn tiếp nhận phản hồi nghiêm túc.

**29. “Không cần Retrospective nếu Review đã có nhiều lỗi.”** Review tập trung sản phẩm/giá trị; Retrospective tập trung cải tiến cách Scrum Team làm việc.

**30. “Tổ chức Agile càng nhiều gate sẽ càng an toàn.”** Gate cần bảo vệ rủi ro thật và quyền rõ; gate không có bằng chứng có thể chỉ tạo hàng chờ.

### 30.1. Nhận diện kiểu ngộ nhận theo triệu chứng

| Triệu chứng trong tổ chức | Ngộ nhận có thể đứng sau | Câu hỏi sửa cách hiểu |
| --- | --- | --- |
| Tất cả ticket được Done vào một ngày cuối Sprint | 1, 2, 15, 25 | Done theo DoD hay theo lịch họp? |
| Stakeholder chỉ gặp nhóm mỗi hai tuần | 7, 8, 27 | Có kênh học hỏi sớm nào phù hợp? |
| Demo xanh nhưng có lỗi dữ liệu | 6, 9, 10, 11 | Bằng chứng DoD nào thực sự đạt? |
| PO bị yêu cầu ký từng task | 5, 18, 23 | Quyền sản phẩm, kỹ thuật và hợp đồng phân biệt chưa? |
| Góp ý mới làm cả Sprint bị “reject” | 4, 16, 17, 28 | Đây là defect hay khám phá mới? |
| Nhiều nhóm có task Done nhưng luồng không chạy | 20, 21, 22 | Increment có tích hợp đạt DoD không? |
| Release phải chờ “buổi demo” dù không có gate thật | 2, 3, 24, 30 | Điều kiện release cụ thể là gì? |

## 31. Mẫu ghi chú Sprint Review ngắn, không biến thành biên bản nghiệm thu

Một mẫu có thể giúp Review tập trung đúng câu hỏi. Đây là **tài liệu tùy chọn**; không phải artifact Scrum bắt buộc và không thay biểu mẫu hợp đồng.

~~~text
SPRINT REVIEW — GHI CHÚ HỌC HỎI VÀ THÍCH ỨNG

Product Goal:
  ...

Sprint Goal của Scrum Team:
  ...

Increment thực sự đạt DoD:
  - ...

Những PBI chưa đạt DoD (không trình bày như Increment Done):
  - ...

Những Increment đã giao/phát hành trước Review (nếu có):
  - Phạm vi: ...
  - Người dùng được phép: ...
  - Bằng chứng phản hồi: ...

Tiến bộ hướng Product Goal:
  - Outcome quan sát: ...
  - Điều chưa chắc: ...

Phản hồi của stakeholder:
  - Quan sát: ...
  - Bằng chứng hoặc ví dụ: ...
  - Phân loại sơ bộ:
      defect / làm rõ / ý tưởng mới / thay đổi nghĩa vụ

Rủi ro và điều kiện release/contract acceptance:
  - ...

Điều chỉnh Product Backlog cần cân nhắc:
  - ...

Quyết định trong quyền hiện tại:
  - ...

Điều cần người có thẩm quyền khác quyết định:
  - ...

Người phối hợp và điểm kiểm tra tiếp:
  - ...
~~~

### 31.1. Ví dụ điền nhanh

> **Product Goal:** Người học mới đăng ký và bắt đầu học thuận lợi.  
> **Increment Done:** Đăng ký miễn phí, danh sách khóa theo tài khoản.  
> **Released:** Đăng ký đã tới nhóm pilot được phép.  
> **Chưa Done:** Mở bài đầu còn lỗi phân quyền.  
> **Phản hồi:** Người học khó tìm đường mở bài, chưa rõ hướng dẫn.  
> **Học hỏi:** Chuyển đổi từ đăng ký sang bắt đầu học là điểm rơi.  
> **Cân nhắc backlog:** Cải thiện điều hướng, sửa và kiểm chứng quyền học.  
> **Quyền:** Product Owner xem thứ tự PBI; security/release theo quy trình riêng.  
> **Không kết luận:** Buổi Review này không đồng nghĩa hợp đồng đã được nghiệm thu.

### 31.2. Không biến mẫu thành một bộ giấy tờ nặng nề

Nếu một Review 45 phút cần thêm nhiều giờ viết biên bản chỉ để sao chép trạng thái ticket, mẫu đã mất tác dụng. Ghi **đủ điều để tiếp tục hành động và truy vết quyết định cần thiết**, không lập hồ sơ chỉ vì hình thức.

## 32. Mẫu chính sách tách DoD, release và nghiệm thu

Nhóm có thể cùng stakeholders và những người có thẩm quyền liên quan viết thỏa thuận ngắn về ba quyết định.

~~~text
1. Trạng thái Done:
   PBI được gọi Done khi đáp ứng Definition of Done của sản phẩm.
   Không cần đợi Sprint Review mới ghi nhận bằng chứng đã đạt DoD.

2. Phản hồi sản phẩm:
   Scrum Team có thể làm rõ nhu cầu và thu phản hồi thường xuyên
   với người được phép, dùng môi trường và dữ liệu phù hợp.

3. Sprint Review:
   Kiểm tra kết quả Sprint và Product Goal, thảo luận các thay đổi
   có giá trị; không dùng như cổng release mặc định.

4. Release:
   Quyết định giao/phát hành căn cứ vào Increment đạt DoD
   và các điều kiện release được tổ chức phê duyệt.

5. Nghiệm thu hợp đồng:
   Thực hiện theo baseline, bằng chứng, hình thức và người ký
   có thẩm quyền. Không mặc định Sprint Review là biên bản nghiệm thu.

6. Phản hồi mới:
   Phân loại defect, làm rõ, cơ hội mới, hoặc thay đổi nghĩa vụ;
   ghi vào Product Backlog/decision log theo đúng quyền.

7. Rủi ro:
   Khi có lỗi dữ liệu, an toàn hoặc chất lượng nghiêm trọng,
   xử lý ngay theo chính sách; không đợi sự kiện định kỳ.
~~~

### 32.1. Ai cần cùng xây chính sách?

- Developers và Product Owner để xác định Done và kênh feedback.
- Scrum Master để hỗ trợ Scrum đúng mục đích.
- Đại diện người dùng/stakeholders để kênh feedback khả thi.
- Vận hành/security/privacy nếu điều kiện release/dữ liệu liên quan.
- Contract manager/procurement nếu có nghĩa vụ nghiệm thu và thay đổi hợp đồng.

**Không phải mọi bên đều cần ký vào cùng một tờ giấy.** Cần xác định quyền và quy trình phù hợp, tránh việc chính sách mới vô tình tạo thêm một “gate phê duyệt chính sách” cho từng PBI.

### 32.2. Khi tổ chức có chuẩn DoD chung

Không được hạ chuẩn bắt buộc ở cấp nhóm. Nếu nhiều Scrum Teams cùng sản phẩm, dùng một Definition of Done chung. Khi cần nâng chuẩn để khắc phục những lỗi lặp lại, nhóm cần đánh giá tác động, năng lực và chuẩn tổ chức áp dụng.

### 32.3. Đừng tuyên bố “release tự động” nếu chưa có quyền

Khả năng CI/CD tự động tốt có thể giúp giao thường xuyên, nhưng việc production release vẫn phải tuân chính sách. Một pipeline có nút deploy không đồng nghĩa Developers có quyền bỏ kiểm soát an toàn và dữ liệu.

## 33. Kế hoạch cải tiến qua hai Sprint để bỏ cổng Review giả tạo

Một thay đổi quy trình nên được xem như **thử nghiệm có giả thuyết**, không chỉ phát biểu “từ mai Review không cần duyệt nữa”.

### 33.1. Plan — xác định vấn đề và giả thuyết

**Vấn đề:** Nhiều Increment đã đạt DoD phải chờ tới cuối Sprint mới có phản hồi hoặc được giao, dù không có điều kiện release bắt buộc tương ứng.

**Giả thuyết:** Nếu tách DoD khỏi Review, thu phản hồi trong Sprint và giữ gate có rủi ro thật ở quy trình riêng, thời gian tới feedback và release có thể giảm mà không làm tăng lỗi/vi phạm.

**Baseline cần đo:** Done-to-feedback wait, Done-to-release wait, số item còn dở già đi, lỗi sau phát hành, quality gate, phản hồi Product Goal.

### 33.2. Do — thử trong phạm vi được phép

Sprint 1:

1. Thống nhất ý nghĩa DoD, release, Review và nghiệm thu với người liên quan.
2. Chọn một dòng giá trị nhỏ và những user stories có thể thử sớm.
3. Chuẩn bị acceptance examples, CI và dữ liệu test an toàn.
4. Mời người dùng được phép preview **sau khi lát cắt đủ điều kiện**, không đợi buổi Review.
5. Ghi phản hồi và phân loại; release theo chính sách.
6. Review cuối Sprint tập trung Product Goal, kết quả và backlog.

Sprint 2:

1. Tiếp tục xem thời gian chờ và các điểm nghẽn.
2. Cải thiện kênh phản hồi/điều kiện test đã lộ ra trong Sprint 1.
3. Xem liệu có PBI bị giữ không cần thiết ở bước phê duyệt.
4. Xem các trường hợp ngoại lệ cần quy trình an toàn/hợp đồng.
5. Đánh giá kết quả theo cả tốc độ, chất lượng và outcome.

**Không phải mọi tổ chức đều đủ dữ liệu sau hai Sprint để kết luận bền vững**. Mục tiêu trước mắt là học về cơ chế chờ, không báo ROI chắc chắn.

### 33.3. Study — xem dữ liệu và những tác dụng phụ

Giả sử trước thử, thời gian chờ từ DoD tới feedback của 8 lát cắt là:

~~~text
1, 2, 3, 4, 5, 6, 7, 8 ngày làm việc
~~~

Sau thử với 8 lát cắt khác, cách ghi nhận nhất quán:

~~~text
0, 0, 1, 1, 1, 2, 2, 3 ngày làm việc
~~~

| Metric minh họa | Trước | Sau |
| --- | ---: | ---: |
| Số lát cắt | 8 | 8 |
| Tổng ngày-item chờ feedback | 36 | 10 |
| Trung bình | 4,5 ngày | 1,25 ngày |
| Trung vị | 4,5 ngày | 1 ngày |
| Lát cắt chờ quá 3 ngày | 5/8 | 0/8 |

Kiểm tra:

\[
0+0+1+1+1+2+2+3=10
\quad;\quad
\frac{10}{8}=1{,}25
\]

**Dữ liệu hoàn toàn giả định.** Không thể chỉ từ hai mẫu nhỏ mà kết luận thay chính sách là nguyên nhân duy nhất. Loại công việc, độ khó, lịch stakeholder, điều kiện môi trường và sự cố giữa kỳ có thể khác. Phải xem thêm quality guardrails và Work Item Age của những item chưa đạt DoD.

### 33.4. Guardrails cần thiết

- Không có tăng bất thường lỗi dữ liệu/permission.
- DoD không bị hạ hoặc ghi Done sai.
- Release policy và hợp đồng được tôn trọng.
- Người dùng được thử sản phẩm trong phạm vi quyền dữ liệu.
- CI và môi trường test giữ độ tin cậy.
- Thành viên không phải bù bằng làm thêm quá sức kéo dài.
- Feedback thật có giúp Product Backlog hoặc Product Goal không?

### 33.5. Act — quyết định giữ hoặc điều chỉnh

Nếu feedback đến sớm, chất lượng không xấu và Product Backlog được điều chỉnh có căn cứ, nhóm có thể đưa nguyên tắc vào working agreement và tiếp tục theo dõi.

Nếu dữ liệu chỉ đẹp vì **các PBI khó vẫn nằm ở WIP**, cần xem Work Item Age và điều kiện phát hành, không vội tuyên bố thành công.

Nếu một gate bảo mật thật tạo chờ, mục tiêu cải tiến là **chuẩn bị bằng chứng và làm rõ quyền**, không xóa gate trái quy định.

## 34. Bộ câu hỏi nhanh để kiểm tra một “cổng Review” có đang sai mục đích

| Câu hỏi | Dấu hiệu của cách làm hợp lý | Dấu hiệu cần điều tra |
| --- | --- | --- |
| **Ai quyết định Done?** | DoD và bằng chứng chất lượng | Người dự họp ký theo cảm tính |
| **Increment Done có thể giao sớm?** | Có nếu đủ điều kiện release | Phải chờ buổi Review trong mọi trường hợp |
| **Phản hồi có tới giữa Sprint?** | Có kênh an toàn và đúng người | Mọi câu hỏi đều bị dời tới Review |
| **Review nói về gì?** | Product Goal, kết quả, dữ liệu, thích ứng | Đọc status và phê duyệt ticket |
| **Phát hiện mới được xử lý sao?** | Phân loại và cập nhật Product Backlog | Gọi mọi ý kiến là lỗi nghiệm thu |
| **Chất lượng được kiểm chứng khi nào?** | Tích hợp/test thường xuyên theo DoD | Chờ demo để “người dùng tự kiểm tra” |
| **Release gate thực sự là gì?** | Điều kiện rủi ro và người quyết định rõ | Chỉ là lịch cuối Sprint, không có căn cứ |
| **Contract acceptance có được phân biệt?** | Theo nghĩa vụ/thủ tục riêng | Sprint Review tự được coi là chữ ký |
| **Metrics có trung thực?** | Tách DoD, release, feedback, acceptance | Một cột Done lẫn bốn ý nghĩa |
| **Nhiều nhóm cùng sản phẩm?** | Có Increment tích hợp và DoD chung | Tổng các mảnh UI/API/DB được tính Done |

Nếu phần lớn câu trả lời nằm ở cột phải, vấn đề có thể là **cấu trúc công việc, quyền, văn hóa và cách hiểu Scrum**, không chỉ tên cuộc họp.

## 35. Checklist thực hành: Sprint Review không thành cổng nghiệm thu duy nhất

### A. Trước Sprint và trong refinement

1. **Product Goal:** Người học nào nhận giá trị, kết quả muốn đạt là gì?
2. **Sprint Goal:** Có hướng Sprint rõ, không chỉ danh sách ticket?
3. **Acceptance examples:** Hành vi bình thường và tình huống lỗi đã được trao đổi?
4. **DoD:** Chất lượng cần đạt đã rõ và được áp dụng nhất quán?
5. **Quyền:** PO, Developers, stakeholder, security/release và contract authority khác nhau ở đâu?
6. **Hợp đồng:** Có nghĩa vụ, nghiệm thu hoặc release gate riêng cần chuẩn bị?
7. **Kênh feedback:** Người dùng được phép thử sớm ở đâu, bằng dữ liệu nào?
8. **Người liên quan:** Có thể hỏi trực tiếp khi cần làm rõ thay vì đợi Review?

### B. Trong Sprint

9. **Vertical slice:** Đang xây hành vi có thể dùng thay vì từng tầng kỹ thuật rời?
10. **CI/test:** Tích hợp và kiểm chứng diễn ra thường xuyên?
11. **Blocker:** Có giải quyết phụ thuộc và lỗi ngay khi phát hiện?
12. **Trạng thái Done:** Chỉ công nhận khi đạt DoD, không theo lịch họp?
13. **Chưa Done:** Không giả rằng code xong là Increment?
14. **Giao sớm:** Increment Done đủ điều kiện có thể tới người dùng trước Review?
15. **An toàn:** Release policy và dữ liệu nhạy cảm vẫn được bảo vệ?
16. **Feedback sớm:** Có thể thử với người dùng/đại diện được phép trong Sprint?
17. **Phân loại phản hồi:** Lỗi, làm rõ, cơ hội mới hoặc thay đổi hợp đồng?
18. **Không tự hứa:** Feedback mới chưa tự thành commitment hoặc thay scope?

### C. Tại Sprint Review

19. **Mục đích:** Cùng inspect kết quả và adapt hướng sản phẩm?
20. **Kết quả:** Chỉ giới thiệu phần Increment thực sự đạt DoD như Done?
21. **Tích hợp:** Với nhiều nhóm, xem sản phẩm tích hợp thay vì mảnh rời?
22. **Progress:** Có thảo luận tiến độ hướng Product Goal?
23. **Outcome:** Có xem dữ liệu sử dụng/quan sát với giới hạn rõ?
24. **Không chấm điểm:** Review không biến thành phiên xin chữ ký từng task?
25. **Không là release gate:** Không bắt mọi Increment chờ đến cuối Sprint nếu không có nghĩa vụ?
26. **Không là nghiệm thu hợp đồng:** Thủ tục pháp lý được giữ riêng đúng quyền?
27. **Thảo luận:** Stakeholders có cùng xem cơ hội/rủi ro và hướng tiếp theo?
28. **Backlog:** Product Owner có thông tin để điều chỉnh thứ tự/làm rõ PBI?
29. **Quyền:** Điều cần thay hợp đồng/security/release được đưa đúng người?

### D. Sau Sprint Review

30. **Phản hồi:** Các ghi chú có phân loại và người theo dõi thay vì “Accepted/Rejected” đơn giản?
31. **Done vẫn rõ:** Không đổi trạng thái PBI chỉ vì có ý kiến mới không vi phạm tiêu chí?
32. **Defect thật:** Nếu phát hiện sai DoD, có xử lý theo mức độ và rủi ro?
33. **Release:** Tình trạng Done, ready-for-release, released được tách nếu cần?
34. **Contract acceptance:** Có bằng chứng và người ký theo quy định thực?
35. **Flow metrics:** Work Item Age, Cycle Time và Done-to-release wait có ranh giới đo?
36. **Quality guardrail:** Giao sớm hơn có làm xấu dữ liệu, bảo mật hoặc vận hành?
37. **Retrospective:** Nhóm có học cách giảm chờ và cải thiện chất lượng feedback?
38. **Liên tục:** Không đợi Review kế tiếp mới giải quyết sự cố hoặc câu hỏi quan trọng?

## 36. Tổng kết: Review là nơi học và thích ứng, không phải chiếc khóa giữ Increment

Sprint Review có giá trị lớn khi Scrum Team và stakeholders dùng nó để **xem phần mềm thực sự đã tạo ra, hiểu tiến độ tới Product Goal, học từ sử dụng và xác định điều chỉnh tương lai**. Sự kiện này mất giá trị khi bị biến thành cuộc họp duy nhất có quyền cho phép mọi PBI Done, mọi Increment phát hành hoặc mọi đầu ra hợp đồng được nghiệm thu.

| Sai lầm | Cách làm đúng mục đích hơn |
| --- | --- |
| Chờ khách hàng ký tại Review mới đánh dấu Done | Xác minh Increment theo **Definition of Done** |
| Không cho ai thử phần mềm trước cuối Sprint | Nhận feedback sớm qua kênh, dữ liệu và quyền được phép |
| Gọi prototype/demo là Increment đã hoàn tất | Phân biệt prototype, task hoàn tất và Increment đạt DoD |
| Lấy Review thay test và review kỹ thuật | Tích hợp, kiểm thử và xử lý rủi ro liên tục |
| Dùng Review làm cổng release mặc định | Giao sớm nếu đủ điều kiện, quản lý gate thực sự riêng |
| Dùng Review làm chữ ký nghiệm thu hợp đồng | Truy vết nghĩa vụ và thực hiện thủ tục theo thẩm quyền |
| Coi mọi phản hồi là lỗi làm Sprint bị reject | Phân loại defect, làm rõ, cơ hội mới và thay đổi nghĩa vụ |
| Chỉ xem task/points trong Review | Xem **Sprint Goal, Product Goal, Increment và outcome** |
| Đo Done theo lịch họp | Tách **DoD, release, feedback và nghiệm thu** bằng dữ liệu rõ |
| Che item chưa Done để có buổi Review đẹp | Minh bạch rủi ro, Work Item Age, DoD và hướng xử lý |
| Chỉ nhóm kỹ thuật được nói, stakeholder chỉ duyệt | Cùng trao đổi về giá trị, giả định và lựa chọn tương lai |
| Bỏ gate an toàn vì nghĩ “Agile không cần duyệt” | Giữ đúng gate thật, chuẩn bị bằng chứng sớm và giảm chờ hợp lệ |

**Ghi nhớ:** Một dòng công việc lành mạnh đi theo **Làm rõ nhu cầu → Phát triển và tích hợp → Kiểm chứng Definition of Done → Giao Increment khi các điều kiện áp dụng cho phép → Nhận phản hồi liên tục → Dùng Sprint Review để kiểm tra và thích ứng Product Backlog → Cải tiến trong Retrospective**. Nếu cần nghiệm thu hợp đồng hoặc phê duyệt an toàn, hãy đặt các quyết định ấy **đúng phạm vi và thẩm quyền**, không đồng nhất chúng với Scrum Review.

Trong **AGILE_DEVELOPMENT**, **Scrum** cung cấp mục tiêu, trách nhiệm và sự kiện inspect/adapt; **Kanban** giúp thấy WIP, tuổi công việc và hàng chờ phê duyệt; **XP/CI** giúp chất lượng được kiểm chứng sớm; **user story và Product Backlog** giúp đối thoại và ưu tiên những lát cắt thật sự có giá trị. **Sprint Review không phải cổng nghiệm thu duy nhất; đó là một điểm cộng tác quan trọng trong vòng phản hồi liên tục để giao phần mềm tăng dần, an toàn và thích ứng với nhu cầu người dùng.**
