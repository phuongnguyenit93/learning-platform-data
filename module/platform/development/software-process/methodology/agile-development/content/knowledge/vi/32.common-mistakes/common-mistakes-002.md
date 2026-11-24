# Đồng nhất Agile với Scrum hoặc một bộ công cụ

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Phân biệt **Agile** như tập giá trị và nguyên tắc với **Scrum** như framework, **Kanban/XP** như các cách thực hành có trọng tâm riêng và **công cụ** như phương tiện hỗ trợ.
2. Giải thích vì sao **có Sprint, Daily Scrum, bảng task, story point hoặc phần mềm quản lý dự án** chưa đủ chứng minh một nhóm đang tạo ra giá trị theo tư duy Agile.
3. Nhận diện sai lầm **Scrum máy móc, Scrum chỉ có tên, Scrumfall, chạy theo velocity, dùng công cụ để giám sát cá nhân** và tác động của chúng tới phản hồi, chất lượng, khả năng thích nghi.
4. Nêu đúng **các trách nhiệm, sự kiện, tạo tác và cam kết của Scrum** khi đội thực sự chọn Scrum, không gọi tùy ý một cuộc họp status là Daily Scrum.
5. Phân tích cách **Kanban, XP và thực hành kỹ thuật** bổ sung hoặc thay thế một số cách phối hợp theo loại công việc mà không tự nhận mọi thứ là Scrum.
6. Đề xuất cách lựa chọn và thử nghiệm phương pháp dựa trên **loại công việc, mức bất định, phụ thuộc, rủi ro, phản hồi người dùng và quyền quyết định**.
7. Thiết kế các tín hiệu đo **dòng công việc, chất lượng, kết quả người dùng và học hỏi** để cải tiến, không biến Agile thành bộ chỉ số thành tích.

## 1. Sai lầm: “Có Scrum hoặc Jira tức là đã Agile”

Một nhóm phát triển nền tảng học trực tuyến được yêu cầu “chuyển sang Agile”. Họ triển khai phần mềm quản lý công việc, chia dự án thành Sprint hai tuần, bắt đầu họp mỗi sáng và đặt số story point cho mọi ticket.

Sau ba tháng:

- Product Owner vẫn chỉ nhận yêu cầu đã chốt từ đầu quý; người dùng chưa được thử Increment nào thực sự sử dụng được.
- Các nhóm UI, API và kiểm thử làm riêng, tới cuối Sprint mới tích hợp; rất nhiều ticket “Done” nhưng tính năng chưa chạy.
- Daily Scrum trở thành buổi từng người đọc trạng thái cho quản lý.
- Story point bị biến thành chỉ tiêu phải đạt; thành viên tránh các việc khó có nguy cơ không hoàn tất.
- Phản hồi từ học viên được ghi ở một bảng khác và không ảnh hưởng Product Backlog.

Nhóm có **hình thức** Scrum và công cụ, nhưng các quyết định quan trọng vẫn không thay đổi: yêu cầu bị khóa, feedback đến muộn, chất lượng kiểm tra ở cuối, rủi ro bị che.

> **Ngộ nhận cốt lõi:** Nhầm **tên phương pháp, cuộc họp, vai trò, nhãn trạng thái và tính năng phần mềm** với khả năng tổ chức phản hồi sớm, giao giá trị tăng dần và cải tiến dựa trên thực tế.

Giải pháp không phải xóa hết Sprint hoặc bỏ công cụ. Cần hỏi **những hành vi nào đang giúp nhóm học và thích nghi**, những nghi thức nào chỉ làm công việc cũ trông giống Agile.

### Câu hỏi mở đầu

Nếu ngày mai tổ chức tắt phần mềm quản lý công việc trong một ngày, nhóm có còn:

1. Biết **mục tiêu người dùng/sản phẩm** cần đạt?
2. Có thể giải thích **phần nào đã chạy và đạt chất lượng**, phần nào chưa?
3. Nhận được và xử lý **phản hồi đáng tin**?
4. Phối hợp để xử lý **blocker và phụ thuộc**?
5. Có quyền và khả năng **điều chỉnh kế hoạch** khi học được điều mới?

Nếu câu trả lời là “không” cho hầu hết câu hỏi, thêm biểu đồ hay automation có thể chỉ che vấn đề nền.

## 2. Sơ đồ khái niệm: Agile, framework, thực hành và công cụ

Nhiều người dùng các từ **Agile, Scrum, Kanban, XP, DevOps, Jira, Sprint** như thể đồng nghĩa. Thực tế chúng nằm ở các cấp khái niệm khác nhau.

| Cấp | Nội dung | Câu hỏi chính | Ví dụ |
| --- | --- | --- | --- |
| **Giá trị và nguyên tắc Agile** | Cách ưu tiên con người, giá trị, phản hồi và thích nghi | Vì sao chúng ta tổ chức công việc theo cách này? | Hợp tác với người dùng, giao phần mềm hoạt động, cải tiến liên tục |
| **Framework/phương pháp phối hợp** | Cấu trúc trách nhiệm và cơ chế điều phối | Nhóm tổ chức ra quyết định, công việc và phản hồi thế nào? | Scrum, Kanban Method và các cách tổ chức khác theo phạm vi phù hợp |
| **Thực hành kỹ thuật và sản phẩm** | Những hành vi cụ thể hỗ trợ chất lượng, học hỏi, flow | Làm thế nào phát triển, kiểm thử, tích hợp và khám phá tốt hơn? | XP, TDD, CI, pairing, refinement, slicing, user story mapping |
| **Công cụ** | Hệ thống, bảng và automation hỗ trợ hành vi | Dữ liệu, cộng tác và kiểm chứng được thực hiện ở đâu? | Bảng giấy, Jira, Trello, GitHub Issues, CI server |
| **Kết quả thực** | Bằng chứng tạo giá trị và có khả năng thích nghi | Người dùng và hệ thống làm việc được cải thiện ra sao? | Task success, chất lượng Increment, thời gian phản hồi, lỗi phát hiện sớm |

**Một công cụ có thể hỗ trợ nhiều cách làm**; cùng Jira có thể quản lý Scrum, Kanban, việc theo kế hoạch truyền thống hoặc hàng đợi hỗ trợ. Tên phần mềm không xác nhận tư duy Agile của người dùng nó.

### Một sơ đồ tư duy

~~~mermaid
flowchart TD
    A["Giá trị và nguyên tắc Agile"] --> B["Quyết định về cách hợp tác và học hỏi"]
    B --> C["Scrum nếu phù hợp"]
    B --> D["Kanban nếu phù hợp"]
    B --> E["Cách phối hợp khác có kiểm chứng"]
    C --> F["Thực hành kỹ thuật, sản phẩm và phản hồi"]
    D --> F
    E --> F
    F --> G["Công cụ và tự động hóa tùy nhu cầu"]
    G --> H["Bằng chứng: giá trị, chất lượng, flow, học hỏi"]
    H --> B
~~~

Các mũi tên thể hiện **mối quan hệ lựa chọn và phản hồi**, không phải Agile chính thức chỉ có ba nhánh. Có thể kết hợp các thực hành tương thích, nhưng phải hiểu **cấu trúc và nghĩa vụ** của framework đang tuyên bố sử dụng.

## 3. Agile là giá trị và nguyên tắc, không phải một lịch họp

Tuyên ngôn phát triển phần mềm Agile nêu bốn giá trị với ý nghĩa **ưu tiên những điều bên trái hơn**, không phủ nhận giá trị của các điều bên phải:

| Ưu tiên cao hơn | Vẫn có giá trị |
| --- | --- |
| **Cá nhân và tương tác** | Quy trình và công cụ |
| **Phần mềm chạy được** | Tài liệu đầy đủ |
| **Cộng tác với khách hàng** | Đàm phán hợp đồng |
| **Phản hồi với thay đổi** | Bám sát kế hoạch |

### Diễn giải trong thực tế

**Cá nhân và tương tác hơn quy trình/công cụ:** Nếu review bị chặn, một cuộc trao đổi trực tiếp giữa đúng người có thể hữu ích hơn thêm trạng thái “Pending Escalation”. Tuy nhiên, quyền truy cập và dấu vết bắt buộc vẫn phải được giữ.

**Phần mềm chạy được hơn tài liệu đầy đủ:** Một demo có thể kiểm chứng hành vi thực cung cấp bằng chứng tốt về tiến triển. Nhưng tài liệu hợp đồng API, migration và bảo mật vẫn có thể là phần chất lượng bắt buộc.

**Cộng tác với khách hàng hơn đàm phán hợp đồng:** Phản hồi thường xuyên giúp làm rõ nhu cầu và ưu tiên. Không có nghĩa vi phạm cam kết hợp đồng hoặc tự ý bỏ nghĩa vụ pháp lý.

**Phản hồi với thay đổi hơn bám sát kế hoạch:** Kế hoạch là giả thuyết hiện tại, có thể điều chỉnh khi có thông tin mới. Không có nghĩa “không cần lập kế hoạch” hay thay mục tiêu hằng ngày mà không giải thích.

### Cách kiểm tra một hành vi có theo tinh thần Agile

Hãy hỏi:

- Có giúp phát hiện điều chưa biết sớm hơn không?
- Có làm tăng khả năng giao **phần mềm sử dụng được** với chất lượng không?
- Có tạo đối thoại thực chất với người nhận giá trị không?
- Có cho phép điều chỉnh theo bằng chứng mà không làm mất trách nhiệm không?
- Có giảm thời gian chờ, lô việc lớn và sự phụ thuộc không cần thiết không?

**Agile không có nghĩa loại bỏ cấu trúc.** Cấu trúc chỉ nên giúp con người phối hợp và phản hồi, không trở thành mục đích tự thân.

## 4. Các nguyên tắc Agile và lỗi “làm đúng nghi thức”

Mười hai nguyên tắc Agile không chỉ nói về họp hay quản lý backlog. Có thể nhóm theo những chiều giúp người học kiểm tra cách làm:

| Chiều | Tinh thần nguyên tắc | Dấu hiệu đang bỏ sót |
| --- | --- | --- |
| **Giá trị và phản hồi** | Ưu tiên làm hài lòng người dùng bằng giao phần mềm có giá trị sớm và liên tục | Một năm chỉ đo % task hoàn thành, không có người dùng thử |
| **Thích nghi** | Đón nhận thay đổi giúp khách hàng có lợi thế, kể cả khi đã phát triển | Backlog bị khóa chỉ vì “đã lập kế hoạch quý” |
| **Phần mềm hoạt động** | Giao thường xuyên, dùng hoạt động thực làm bằng chứng | Slide xanh, code chưa tích hợp, chưa đạt DoD |
| **Cộng tác** | Người hiểu nghiệp vụ và người phát triển phối hợp liên tục | Yêu cầu được gửi qua nhiều tầng không đối thoại |
| **Con người và tin cậy** | Tạo môi trường hỗ trợ, trao trách nhiệm cho người có năng lực | Người thực hiện chỉ nhận mệnh lệnh từng task |
| **Trao đổi hiệu quả** | Ưu tiên trao đổi trực tiếp khi hữu ích | Mọi câu hỏi phải qua biểu mẫu dài dù người quyết định ngồi cạnh |
| **Đo tiến triển** | Phần mềm hoạt động là thước đo quan trọng | Story point được xem là giá trị người dùng |
| **Nhịp bền vững** | Giữ tốc độ làm việc duy trì được lâu dài | Sprint nào cũng overtime để đạt velocity |
| **Kỹ thuật tốt** | Chú ý kỹ thuật xuất sắc và thiết kế tốt giúp thích nghi | Bỏ CI/test rồi gọi đó là linh hoạt |
| **Đơn giản** | Tối đa hóa lượng việc không cần làm | Xây đủ mọi tính năng “để sau này có thể cần” |
| **Tự tổ chức** | Nhóm tham gia quyết định cách thực hiện | Quản lý phân công mọi giờ việc trong Daily Scrum |
| **Thường xuyên cải tiến** | Định kỳ nhìn lại và điều chỉnh hành vi | Retrospective có nhưng hành động không được thử |

Không cần biến bảng này thành một bộ checkbox kiểm toán “đã Agile hay chưa”. Nó nhằm giúp đội **nhìn lại mối quan hệ giữa hoạt động và mục đích**.

### Một phép thử quan trọng

Nếu một nghi thức đang được duy trì vì câu trả lời duy nhất là **“Scrum bảo phải làm”**, hãy hỏi ý nghĩa thực của sự kiện đó trong framework. Nếu một buổi có chủ đích không đạt mục tiêu, cần cải thiện **cách sử dụng**, không tùy tiện kết luận phương pháp sai hay hủy cấu trúc mà không tìm hiểu.

## 5. Scrum là một framework cụ thể, không đồng nghĩa toàn bộ Agile

**Scrum** là một framework nhẹ để con người, nhóm và tổ chức tạo giá trị bằng những giải pháp thích nghi đối với vấn đề phức tạp. Scrum dựa trên chủ nghĩa kinh nghiệm và tư duy tinh gọn; cấu trúc của nó gồm **trách nhiệm giải trình, sự kiện, tạo tác và những cam kết**.

### Các thành phần trong Scrum

| Nhóm thành phần | Thành phần chính | Ý nghĩa cần giữ |
| --- | --- | --- |
| **Trách nhiệm giải trình (accountabilities)** | Product Owner, Scrum Master, Developers | Quyền và trách nhiệm rõ; một Scrum Team không có phân cấp nội bộ kiểu các tiểu đội độc lập |
| **Sự kiện (events)** | Sprint, Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective | Cơ chế có mục tiêu rõ để minh bạch, kiểm tra, thích nghi |
| **Tạo tác (artifacts)** | Product Backlog, Sprint Backlog, Increment | Minh bạch các đối tượng nhóm kiểm tra |
| **Cam kết (commitments)** | Product Goal, Sprint Goal, Definition of Done | Định hướng dài hạn, mục tiêu Sprint, chất lượng Increment |

### Tại sao “có Sprint” không đủ?

Sprint là **khung chứa các sự kiện Scrum và công việc tạo Increment** với mục tiêu. Một đơn vị quản lý có thể dùng “đợt hai tuần” để gom task mà không có Product Goal, Sprint Goal, Increment hay phản hồi; đó **không tự chứng minh đang dùng Scrum đúng hoặc Agile hiệu quả**.

### Hai sự thật cần giữ cùng lúc

1. **Scrum không phải toàn bộ Agile:** Có nhóm dùng Kanban, XP hoặc cách phát triển thích nghi khác mà không dùng Scrum.
2. **Nếu tuyên bố dùng Scrum, không nên tùy ý bỏ các phần cốt lõi rồi vẫn gọi là Scrum đầy đủ:** Những phần của Scrum được thiết kế để bổ sung nhau. Thay đổi hoặc bỏ tùy tiện có thể che vấn đề và làm mất cơ chế thực nghiệm.

Không nhất thiết mọi đội phải chọn Scrum. Nhưng **chọn Scrum thì cần hiểu và vận hành Scrum**, thay vì chỉ đổi tên các cuộc họp cũ.

## 6. Đừng biến các trách nhiệm Scrum thành chức danh chỉ để báo cáo

### Product Owner không chỉ là người nhận ticket

Product Owner chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. Người này cần có khả năng làm rõ hướng sản phẩm, thứ tự ưu tiên, mục tiêu và trao đổi với stakeholders.

**Ngộ nhận:** “Product Owner là nhân viên nhập yêu cầu từ quản lý vào Jira; quyền ưu tiên thuộc một hội đồng khác nhưng không ai biết.”

**Hệ quả:** Backlog trở thành danh sách đơn đặt hàng; những phản hồi mới không thể làm thay đổi quyết định; trách nhiệm về giá trị không rõ.

### Scrum Master không phải thư ký, cảnh sát quy trình hoặc project manager đổi tên

Scrum Master chịu trách nhiệm về hiệu quả Scrum Team và thiết lập Scrum như được định nghĩa trong Scrum Guide. Họ hỗ trợ Scrum Team, Product Owner và tổ chức nâng cao khả năng làm việc theo Scrum.

**Ngộ nhận:** “Scrum Master phải đọc ticket từng người, ép cập nhật story point và báo cáo ai không làm đủ.”

**Hệ quả:** Daily Scrum thành phiên kiểm điểm; thông tin blocker và rủi ro không còn được chia sẻ trung thực.

### Developers không phải người chờ phân công từng dòng việc

Developers chịu trách nhiệm lập kế hoạch công việc trong Sprint, chất lượng theo Definition of Done, thích nghi kế hoạch hướng Sprint Goal và chịu trách nhiệm với nhau như những người chuyên nghiệp.

**Ngộ nhận:** “Quản lý phải chỉ rõ ai code gì, bao lâu; Developers chỉ thực hiện.”

**Hệ quả:** Nhóm khó tự điều chỉnh khi xuất hiện phụ thuộc, lỗi hoặc điều mới học được.

### Một ví dụ thay đổi hành vi

Thay vì:

> “Quản lý chia ticket, Scrum Master hỏi % hoàn thành, Product Owner ký khi cuối Sprint.”

Hãy hướng tới:

> “Product Owner nêu mục tiêu và thứ tự giá trị; Developers cùng xây kế hoạch và tự phối hợp để tạo Increment đạt DoD; Scrum Master giúp nhận diện những trở ngại đối với hiệu quả Scrum.”

Đây là sự thay đổi **trách nhiệm và quyền quyết định**, không chỉ tên chức danh.

## 7. Đừng biến sự kiện Scrum thành các cuộc họp status

| Sự kiện | Mục đích chính | Cách dùng sai thường gặp |
| --- | --- | --- |
| **Sprint Planning** | Xác định tại sao Sprint có giá trị, có thể làm gì và làm thế nào; hình thành Sprint Goal | Quản lý giao sẵn mọi task và đòi cam kết số point bất kể bất định |
| **Daily Scrum** | Developers kiểm tra tiến triển hướng Sprint Goal và điều chỉnh Sprint Backlog | Từng người báo cáo hôm qua/hôm nay/khó khăn cho cấp trên, không thay kế hoạch |
| **Sprint Review** | Kiểm tra kết quả Sprint với stakeholders, thích nghi hướng sản phẩm | Demo slide để “được ký duyệt”, không có phản hồi hoặc Increment hoạt động |
| **Sprint Retrospective** | Lập kế hoạch nâng chất lượng và hiệu quả | Ai cũng phàn nàn; action cũ không bao giờ được xem lại |
| **Sprint** | Nhịp tạo giá trị, chứa công việc và các sự kiện | Chia dự án thành “Sprint phân tích”, “Sprint code”, “Sprint test” rồi mới ghép ở cuối |

**Daily Scrum** là sự kiện 15 phút dành cho Developers. Một câu hỏi như “Hôm qua làm gì?” có thể hữu ích trong một số bối cảnh, nhưng nó **không phải mục tiêu hay mẫu báo cáo bắt buộc** của Daily Scrum.

### Sprint Review không phải cổng phê duyệt để gọi sản phẩm Done

Increment đáp ứng **Definition of Done** có thể được giao trước Sprint Review; Review là cơ hội kiểm tra và điều chỉnh, không nhất thiết là thời điểm được phép release. Các quy định phát hành của tổ chức có thể tồn tại riêng và cần tuân thủ, nhưng không nên nói **“Scrum bắt buộc chỉ release sau Review”**.

### Một Daily Scrum hướng tới giá trị

Ví dụ Sprint Goal: “Học viên mở được đúng bài gần nhất còn quyền”.

- Story nào đang đe dọa Sprint Goal vì API/kiểm thử chưa thông?
- Có thể ưu tiên review hoặc tích hợp item đã bắt đầu thay vì mở thêm không?
- Chúng ta đã biết điều gì mới về phân quyền hoặc hành vi retry?
- Cần điều chỉnh Sprint Backlog để tạo Increment dùng được không?

Mỗi người không cần đọc một bản báo cáo cố định nếu không giúp quyết định tiến gần Sprint Goal hơn.

## 8. Đừng hiểu sai Product Backlog, Sprint Backlog và Increment

**Product Backlog** không đơn giản là kho ticket được mọi phòng ban gửi vào. Nó là danh sách được sắp xếp, phát triển dần để cải thiện sản phẩm, liên kết với **Product Goal**.

**Sprint Backlog** không đơn thuần là những ticket được khóa cứng đầu Sprint. Nó gồm **Sprint Goal**, các Product Backlog Items được chọn và kế hoạch hành động có thể thích nghi trong Sprint.

**Increment** không đồng nghĩa tổng số task hoặc tổng số commit. Increment là một bước cụ thể hướng Product Goal, có thể sử dụng, đã được kiểm chứng và đáp ứng **Definition of Done**.

### Ví dụ

Ba ticket đã đóng:

- “Giao diện nút Tiếp tục học” — chỉ chạy với mock.
- “API tiến độ” — chưa kiểm tra quyền thực.
- “Cache phiên” — chưa xử lý response từ tài khoản trước.

Đây có thể là những phần công việc kỹ thuật đã tiến triển, nhưng **chưa có lát cắt sản phẩm đủ điều kiện được gọi Increment hoàn thành** nếu các điều kiện sử dụng và DoD chưa đạt.

### Tránh KPI “ticket Done nhiều = giá trị cao”

Một Sprint đóng 40 task nhỏ nhưng không có gì dùng được có thể tạo ít giá trị hơn Sprint đóng 5 PBI có một cải tiến quan trọng được khách hàng xác nhận. **Số lượng item không thay thế mức tác động và chất lượng**.

## 9. Kanban không phải chỉ là một board ba cột

Nhiều người nghĩ:

> “Chúng tôi dùng Kanban vì có To Do, Doing, Done.”

Một bảng trực quan là điểm khởi đầu có ích, nhưng **chưa đủ để thực sự quản lý dòng công việc**. Kanban khuyến khích minh bạch workflow, quản lý WIP, làm rõ chính sách, quản lý flow, vòng phản hồi và cải tiến từng bước.

### Các câu hỏi Kanban quan trọng

- Item nào bắt đầu được tính **work in progress** và khi nào được tính Done?
- Cột Review chứa công việc đang xử lý hay còn một hàng chờ chưa nhìn thấy?
- WIP limit đặt ở đâu và nhóm làm gì **khi chạm giới hạn**?
- Item nào đã già, bị chặn và cần hỗ trợ để hoàn tất?
- Throughput và cycle time cho thấy phân bố thực tế thế nào?
- Loại công việc thường và sự cố khẩn có chính sách khác nhau không?
- Có một vòng thường xuyên để quan sát dữ liệu và thử cải tiến không?

### Cùng bảng, hai cách hành xử

| “Kanban” chỉ có bảng | Kanban hướng dòng chảy |
| --- | --- |
| Mọi người kéo thêm việc mỗi khi mình rảnh | Cân nhắc WIP và ưu tiên hoàn tất trước khi bắt đầu thêm |
| Item cũ nằm chờ Review không ai hỏi | Aging WIP và blocker được nhìn thấy, đội chủ động gỡ |
| Cột chỉ phản ánh cấu trúc phòng ban | Workflow phản ánh luồng thực và chính sách chuyển bước |
| Đo số ticket của mỗi người | Đo flow của hệ thống: WIP, throughput, cycle time, work item age |
| Đổi màu cột khi vấn đề xảy ra | Thử thay đổi chính sách, kiểm tra tác động và guardrail |

### Kanban không tự động thay Scrum

Scrum Team có thể dùng thực hành Kanban để cải thiện flow **trong khi giữ framework Scrum**, bao gồm các trách nhiệm, sự kiện, tạo tác và cam kết. Một đội khác có thể chọn cách **flow-first** không tổ chức Sprint. Hai trường hợp cần được gọi đúng để tránh kỳ vọng sai.

## 10. XP không phải một loại plugin quản lý Sprint

**Extreme Programming (XP)** tập trung mạnh vào những thực hành phát triển phần mềm giúp tạo phản hồi kỹ thuật sớm và chất lượng thay đổi bền vững.

Một số thực hành thường được nhắc tới:

| Thực hành | Vấn đề có thể giải quyết | Điều không nên ngộ nhận |
| --- | --- | --- |
| **Test-Driven Development (TDD)** | Lỗi logic được phát hiện muộn, thiếu khả năng kiểm chứng | Viết vài unit test sau code không tự chứng minh dùng TDD |
| **Pair programming** | Phản hồi chậm, tri thức chỉ ở một người, module khó | Không phải ngồi cạnh nhau mọi giờ mới “Agile” |
| **Continuous Integration** | Lỗi tích hợp lộ quá muộn, nhánh sống lâu | Build xanh không thay kiểm thử hành vi và hợp đồng |
| **Refactoring** | Thiết kế khó thay đổi, trùng lặp và nợ kỹ thuật | Không phải đổi cấu trúc tùy ý khi thiếu test |
| **Simple design** | Xây nhiều thứ chưa cần, khó hiểu và khó sửa | Không phải bỏ các yêu cầu chất lượng hiện có |
| **Small releases/feedback** | Chờ quá lâu mới biết thay đổi có ích không | Phát hành nhỏ vẫn phải đạt chất lượng và quyền truy cập |
| **Collective ownership / shared code understanding** | Một cá nhân thành nút thắt duy nhất | Không đồng nghĩa ai cũng sửa production vô kiểm soát |

XP không chỉ là “viết code nhanh hơn”. Kỹ thuật tốt giúp việc thay đổi theo feedback **ít rủi ro và ít rework hơn**. Một đội có Sprint đẹp nhưng không có kiểm thử đáng tin có thể vẫn rất khó thích nghi.

### Có thể kết hợp Scrum và XP không?

Có. Scrum tổ chức thực nghiệm về **giá trị, trách nhiệm và Increment**; các thực hành XP có thể giúp Developers **tích hợp và đáp ứng DoD**. Không bắt buộc dùng XP mới được gọi Agile; cũng không nên bỏ kỹ thuật cần thiết vì “chỉ cần làm Scrum”.

## 11. Lean, DevOps và các nhãn phương pháp khác

Những cách tư duy và thực hành khác có thể hỗ trợ Agile, nhưng không nên gom tất cả thành tên gọi đồng nghĩa:

| Khái niệm | Trọng tâm điển hình | Quan hệ với Agile |
| --- | --- | --- |
| **Lean** | Tạo giá trị, giảm lãng phí, cải tiến hệ thống và dòng chảy | Nhiều ý tưởng bổ trợ Agile/Scrum/Kanban |
| **DevOps** | Hợp tác phát triển–vận hành, tự động hóa delivery, độ tin cậy và phản hồi sản xuất | Có thể hỗ trợ giao giá trị an toàn hơn; không chỉ là công cụ CI/CD |
| **Product discovery** | Hiểu vấn đề người dùng, kiểm chứng giả thuyết giá trị | Bổ sung cho delivery; không đồng nghĩa tổ chức Sprint |
| **Agile coaching** | Giúp tổ chức quan sát hệ thống và phát triển năng lực thực hành | Không phải đổi nhãn vai trò hoặc ép dùng một mẫu board |
| **Project management truyền thống** | Có thể phù hợp những phạm vi/điều kiện ít bất định và cam kết cụ thể | Không phải “đối thủ đạo đức”; cần lựa chọn quản trị đúng bối cảnh |

Không nên tự nhận **“DevOps = Agile”** chỉ vì đã có một pipeline deploy. Nếu dev và vận hành vẫn đổ trách nhiệm cho nhau, pipeline không tự sửa được ranh giới phối hợp.

## 12. Công cụ chỉ có giá trị khi nâng khả năng hợp tác và học hỏi

Công cụ có thể hỗ trợ tốt:

- Hiển thị Product Backlog, Sprint Backlog hoặc flow board.
- Lưu thảo luận, acceptance criteria và liên kết với test/PR.
- Thấy item già, blocker, WIP, cycle time và trạng thái tích hợp.
- Kết nối phản hồi người dùng với quyết định ưu tiên.
- Tự động hóa kiểm tra, bằng chứng chất lượng và thông tin release.

Nhưng cũng có thể gây **ảo giác quản lý tốt** nếu số trường dữ liệu và biểu đồ che việc đội chưa ra quyết định.

### Trước khi tạo thêm một trường bắt buộc

Hãy hỏi:

1. Ai thực sự dùng thông tin này để đưa ra **quyết định**?
2. Cần cập nhật vào thời điểm nào, với độ chính xác nào?
3. Có thể lấy dữ liệu từ nguồn đã có thay vì bắt người nhập lặp không?
4. Việc ghi trường này có làm đội giấu blocker hay chuyển trạng thái giả không?
5. Có thông tin cá nhân hoặc bí mật kỹ thuật không cần thu thập không?
6. Nếu bỏ trường này, quyết định nào sẽ trở nên kém hơn?

### Một bảng giấy vẫn có thể hỗ trợ Agile

Một nhóm nhỏ dùng bảng giấy, có Product Goal rõ, trao đổi thường xuyên với người dùng, giao phần mềm đạt DoD, giới hạn WIP và cải tiến dựa trên thực tế có thể **phản hồi tốt hơn** một tổ chức có nhiều dashboard nhưng không giao được Increment.

Điều đó không có nghĩa công cụ số là xấu; chỉ là **công cụ phải phục vụ hành vi**, không định nghĩa hành vi.

## 13. Sai lầm: nhầm workflow trong công cụ với cách công việc thực sự đi qua hệ thống

Một board có thể hiển thị:

~~~text
To Do -> In Progress -> Done
~~~

Nhưng công việc thực sự đi qua:

~~~text
Ý tưởng
  -> Chờ làm rõ yêu cầu
  -> Đang phát triển UI
  -> Chờ API phía nhóm khác
  -> Code review
  -> Chờ môi trường kiểm thử
  -> Sửa lỗi tích hợp
  -> Kiểm chứng quyền và dữ liệu
  -> Tích hợp đạt Definition of Done
  -> Quyết định release theo chính sách
~~~

Nếu mọi khoảng chờ bị gộp vào một trạng thái **In Progress**, dashboard không cho đội biết vì sao cycle time tăng. Nếu người quản lý yêu cầu đổi trạng thái sang Done ngay khi code merge, hệ thống đo sẽ **đẹp hơn nhưng mất thông tin thật**.

### Cách khắc phục

- Vẽ dòng việc **từ một item thực tế** thay vì bắt đầu từ template trong phần mềm.
- Xác định rõ **start point, finish point và chính sách chuyển trạng thái**.
- Thấy được những hàng chờ có tác động, kể cả khi không cần tạo một cột cho mọi thao tác nhỏ.
- Ghi blocker với nguyên nhân và thời gian theo chính sách, không dùng trạng thái blocked để quy lỗi.
- Xác định Done gắn với **điều kiện chất lượng thực**, không chỉ thời điểm một người kết thúc phần code của mình.
- Xem WIP, work item age, cycle time và throughput trong cùng một hệ quy chiếu.

### Khi nào cần thay công cụ?

Chỉ khi công cụ **thực sự không hỗ trợ nhu cầu phối hợp hoặc kiểm chứng** và lợi ích vượt chi phí chuyển đổi. Đừng bắt đầu bằng việc mua công cụ mới khi vấn đề nằm ở quyền ưu tiên, cách chia việc hoặc phụ thuộc API chưa được thỏa thuận.

## 14. Sai lầm: “Scrum nhưng bỏ hết phần khó”

Một số tổ chức nói đang dùng Scrum nhưng:

- Product Owner không có quyền quản lý thứ tự Product Backlog.
- Sprint không có Sprint Goal, chỉ là danh sách ticket cố hoàn thành.
- Không có Increment đạt DoD trước cuối dự án.
- Không tổ chức Sprint Review đúng nghĩa với stakeholders.
- Retrospective bị bỏ vì “chưa có thời gian”.
- Developers không thể tự điều chỉnh kế hoạch; mọi thay đổi phải chờ quản lý giao lại.

Đó không phải vấn đề “chưa đúng thuật ngữ”. **Cơ chế thực nghiệm quan trọng đã bị mất**: minh bạch đối tượng cần kiểm tra, cùng mục tiêu, trách nhiệm quyết định, phản hồi và thích nghi.

### Hai con đường có trách nhiệm

**Con đường A – Thực sự thực hành Scrum:** Làm rõ lý do chọn framework; phục hồi trách nhiệm, sự kiện, tạo tác, cam kết và DoD; nâng năng lực phối hợp/kỹ thuật để Increment được tạo ra mỗi Sprint.

**Con đường B – Chọn cách phối hợp khác phù hợp hơn:** Nếu công việc chủ yếu là yêu cầu đến liên tục, sự cố có mức ưu tiên thay đổi nhanh và khó hình thành mục tiêu Sprint theo cách hiện tại, có thể chọn cách **flow-first** với Kanban hoặc một mô hình tổ chức khác được đánh giá theo bối cảnh.

**Không cần cố gọi mọi cách làm là Scrum.** Nhưng cũng không nên bỏ các phần của Scrum rồi xem những khó khăn còn lại là bằng chứng “Scrum không hiệu quả” khi framework chưa được vận hành đầy đủ.

### “ScrumBut” như một tín hiệu cần điều tra

Câu “Chúng tôi dùng Scrum nhưng không thể làm X vì Y” là một lời mời hỏi:

1. X có phải một phần chính thức của Scrum không?
2. Y là **ràng buộc thật, giả định hay thói quen tổ chức**?
3. Có thể xử lý rào cản mà vẫn đạt mục tiêu framework không?
4. Nếu X không thể thực hiện một cách có trách nhiệm, nhóm nên **đổi mô hình** thay vì giữ nhãn?

Không nên dùng “ScrumBut” như một nhãn miệt thị đội khác. Bối cảnh pháp lý, phụ thuộc và vận hành có thể tạo giới hạn thực cần xử lý.

## 15. Sai lầm: Scrumfall – mini-waterfall trong những Sprint

**Scrumfall** là cách gọi không chính thức cho tình huống tổ chức có Sprint nhưng bên trong hoặc giữa các Sprint vẫn vận hành theo các pha lớn tuần tự:

~~~text
Sprint 1: Phân tích toàn bộ yêu cầu
Sprint 2: Thiết kế toàn bộ hệ thống
Sprint 3: Code UI
Sprint 4: Code Backend
Sprint 5: Test tích hợp
Sprint 6: Sửa lỗi và bàn giao
~~~

Một dự án có thể có công việc khám phá, thiết kế hoặc tích hợp có thứ tự phụ thuộc. Sai lầm là **chỉ tạo phần mềm dùng được rất muộn nhưng vẫn tính từng Sprint trước như đã giao Increment**.

### Vì sao nguy hiểm?

- Nhu cầu người dùng được xác minh sau khi đã tiêu nhiều chi phí.
- Giả định API/dữ liệu không được kiểm chứng chung từ đầu.
- Khối lượng rework tăng khi các tầng gặp nhau.
- Tỷ lệ task “hoàn thành” che tỷ lệ phần mềm có thể sử dụng.
- Người thực hiện khó điều chỉnh kế hoạch vì phụ thuộc được phát hiện sát deadline.

### Thiết kế lát cắt tích hợp sớm

Với “Tiếp tục học”, một lát cắt đầu có thể gồm:

1. Người dùng đã đăng nhập mở được **một bài hợp lệ** của chính mình.
2. UI gọi API có hợp đồng đã xác nhận.
3. API kiểm tra quyền bằng nguồn danh tính đúng.
4. Dữ liệu được đọc theo quy tắc nghiệp vụ nhất quán.
5. Kiểm thử chất lượng liên quan đạt; Increment đáp ứng DoD.

Các khả năng như đồng bộ chính xác từng giây video, gợi ý bài tiếp theo hoặc ngoại tuyến có thể được xem xét ở lát cắt sau nếu phù hợp giá trị. **Lát cắt nhỏ hơn không có nghĩa bỏ kiểm tra quyền hay làm sai dữ liệu**.

### Một lưu ý

Không nhất thiết mọi item đều phải tự mình tạo giá trị độc lập hoàn toàn, ví dụ spike khám phá có đầu ra kiến thức. Nhưng khi Scrum Team khẳng định một Product Backlog Item Done và thuộc Increment, **điều kiện DoD phải được đáp ứng**.

## 16. Sai lầm: Agile chỉ có nghĩa “làm nhanh” và “lập kế hoạch ít”

Nhiều tổ chức bắt đầu chuyển đổi bằng kỳ vọng:

> “Sau khi dùng Scrum, mỗi developer phải làm nhiều ticket hơn mỗi tuần.”

Kỳ vọng này nhầm **tốc độ hoạt động cục bộ** với khả năng **giao giá trị ổn định**. Một nhóm có thể code nhanh nhưng phải sửa lỗi tích hợp, làm overtime, chờ phê duyệt hoặc xử lý sự cố production kéo dài.

### Ba sự phân biệt quan trọng

| Dễ nhầm | Cần xem thực tế |
| --- | --- |
| **Busy time** – mọi người luôn bận | **Flow** – việc có đi tới Done ổn định không? |
| **Output** – số task/tính năng được tạo | **Outcome** – người dùng có giải quyết được vấn đề không? |
| **Speed trong một kỳ** – đóng nhiều item | **Sustainable delivery** – chất lượng và nhịp làm việc có duy trì được không? |

### Lập kế hoạch trong Agile

Agile không cấm kế hoạch dài hạn. Đội có thể có:

- **Product Goal** hoặc định hướng kết quả trong một khoảng dài.
- **Backlog được sắp thứ tự** theo giá trị, rủi ro và thông tin hiện có.
- **Rolling-wave planning**: chi tiết hóa việc gần, giữ mức độ mở cho việc xa khi còn nhiều bất định.
- **Sprint Goal** nếu dùng Scrum, giúp giữ một hướng tập trung trong Sprint.
- **Dự báo** dựa trên dữ liệu flow hoặc năng lực thật, nêu rõ giả định và bất định.

Điều khác biệt là kế hoạch được **kiểm tra và thích nghi bằng phản hồi**, không được coi là sự thật bất biến.

### Chi phí của “tốc độ giả”

Nếu đội bỏ test để hoàn tất thêm ba story, rồi mất hai Sprint sửa lỗi production, chỉ số đầu kỳ có thể đẹp nhưng tổng thời gian giao giá trị lại tăng. Vì vậy cần đo **chất lượng và rework cùng tốc độ**.

## 17. Sai lầm: Story point và velocity là thước đo năng suất cá nhân

**Story point** thường là đơn vị ước lượng tương đối được một số đội dùng để thảo luận về kích thước, độ phức tạp, bất định hoặc công sức theo quy ước nội bộ. **Scrum không bắt buộc dùng story point**.

**Velocity** thường được đội tự tính từ tổng ước lượng của các item hoàn thành trong một Sprint. Nó có thể giúp **lập dự báo nội bộ trong những điều kiện phù hợp**, nhưng không phải thước đo giá trị hoặc hiệu suất cá nhân.

### Ví dụ làm rõ

| Sprint | Story points hoàn thành | Tín hiệu khác |
| --- | ---: | --- |
| A | 30 | Một luồng người dùng đạt DoD; nhiều lỗi API được phát hiện sớm |
| B | 42 | Nhiều task nhỏ hơn, một phần được đánh giá lại điểm; lỗi production tăng |
| C | 26 | Đội xử lý một dependency lớn và làm ổn định CI |

Không thể từ bảng này kết luận **B tốt hơn A và C**. Đội có thể đổi cách cho điểm, loại công việc, cỡ item, rủi ro hoặc xử lý sự cố khác nhau.

### Những hành vi méo mó khi bị ép tăng velocity

- Tăng story point ước lượng để “đạt chỉ tiêu”.
- Chia ticket thành nhiều mẩu không có giá trị để tăng số Done.
- Chọn việc dễ, tránh refactoring, bảo mật hoặc sửa lỗi khó.
- Đóng item khi code xong dù chưa đạt Definition of Done.
- Bỏ qua thời gian giúp nhóm khác review vì không “ra point của mình”.

### Dùng ước lượng có trách nhiệm

- Nói rõ **mục đích ước lượng**: dự báo, chia lát cắt, làm rõ bất định hay quyết định ưu tiên.
- Để người thực hiện cùng thảo luận; tránh áp một bảng quy đổi điểm sang giờ như chân lý.
- Dùng dữ liệu lịch sử của **cùng đội và điều kiện tương đồng** nếu cần dự báo.
- Không biến point thành KPI thưởng phạt hoặc bảng xếp hạng giữa các đội.
- Kết hợp throughput, cycle time, chất lượng và kết quả người dùng nếu chúng thực sự giúp quyết định.

Nếu đội không cần story point để ra quyết định, **không có nghĩa đội kém Agile**. Có những nhóm dự báo theo throughput hoặc work-item size/class hợp lý hơn.

## 18. Sai lầm: Mọi đội phải dùng cùng một framework

Ba nhóm cùng thuộc một nền tảng học trực tuyến nhưng có công việc rất khác:

| Nhóm | Đặc trưng | Rủi ro nếu ép một cách làm | Cách có thể cân nhắc |
| --- | --- | --- | --- |
| **Nhóm tính năng sản phẩm** | Cần tạo Increment, phối hợp với Product Owner, khám phá ưu tiên | Sprint chỉ để gom task, không có phản hồi người dùng | Scrum đầy đủ nếu phù hợp; bổ sung Kanban/XP |
| **Nhóm vận hành và sự cố** | Yêu cầu đến liên tục, việc khẩn cần xử lý ngay | Sprint Goal liên tục bị phá bởi incident hoặc buộc trì hoãn sự cố | Flow-first Kanban với chính sách expedite và service quality |
| **Nhóm tích hợp đối tác** | Nhiều phụ thuộc contract và quyết định bên ngoài | Chỉ báo Done cục bộ, lỗi API dồn cuối Sprint | Contract tests, integration thường xuyên, minh bạch blocked, phối hợp theo bối cảnh |

**Không có đáp án tự động chỉ từ tên nhóm.** Đội vận hành vẫn có thể thực hành Scrum nếu có sản phẩm/mục tiêu và điều kiện phù hợp; đội tính năng cũng có thể dùng Kanban. Điều cần xem là **cách làm có giúp nhóm thực hiện trách nhiệm và giao giá trị an toàn hơn không**.

### Phần nên nhất quán trong tổ chức

- Bảo vệ dữ liệu và quyền truy cập.
- Những tiêu chuẩn chất lượng/DoD cần dùng chung cho sản phẩm.
- Hợp đồng liên hệ thống, quy tắc tương thích và quyền quyết định.
- Những nghĩa vụ pháp lý, vận hành và hợp đồng áp dụng.
- Cách minh bạch phụ thuộc và phản hồi khi phối hợp nhiều nhóm.

### Phần có thể tùy biến

- Dùng Sprint hay flow-first nếu điều kiện cho phép.
- WIP limits, nhịp flow review, cách chia story và kỹ thuật ước lượng.
- Công cụ board, cách cập nhật trạng thái và hình thức pairing.
- Loại báo cáo nội bộ cần để hỗ trợ quyết định.

Tôn trọng bối cảnh **không có nghĩa mỗi đội tự ý bỏ kiểm soát chung**. Sự tự chủ tồn tại trong những **guardrail đã được xác nhận**.

## 19. Trường hợp nghiên cứu A: “Chúng tôi có Scrum, sao vẫn không ra Increment?”

### 19.1. Bối cảnh

Một Scrum Team xây chức năng “Tiếp tục học”. Họ có Sprint hai tuần, Planning, Daily, Review và Retrospective. Nhưng ba nhóm chuyên môn làm tuần tự: UI tạo mock, API phát triển riêng, tester chỉ nhận build ngày cuối.

**Dữ liệu giả định sau ba Sprint:**

| Sprint | Task kỹ thuật được đóng | PBI thực sự đạt DoD | Phản hồi người dùng có ích |
| --- | ---: | ---: | --- |
| 1 | 23 | 0 | Chưa có luồng để thử |
| 2 | 31 | 1 | Phản hồi hạn chế từ một demo nội bộ |
| 3 | 27 | 1 | Một bài kiểm thử tác vụ với người học |

Nhìn số task, Sprint 2 có vẻ “năng suất nhất”. Nhưng đội vẫn chưa đạt mục tiêu giao nhiều lát cắt có thể dùng.

### 19.2. Chẩn đoán

- Sprint Planning đang tập trung “mỗi người lấy bao nhiêu ticket”, ít có Sprint Goal chung.
- Các PBI bị chia thành UI/API/test theo phòng ban nên thiếu hành vi xuyên sản phẩm.
- DoD chỉ được kiểm tra khi mọi nhóm báo xong.
- Stakeholders nhận demo muộn; feedback không quay vào thứ tự backlog sớm.
- Dashboard tính code merge là Done, che các item chưa đạt chất lượng.

### 19.3. Thử thay đổi

1. Product Owner và Developers làm rõ một Sprint Goal theo **hành vi người dùng**.
2. Chia một lát cắt xuyên UI–API–quyền có thể kiểm chứng trong Sprint.
3. Thống nhất AC và DoD, bao gồm kiểm tra quyền/tích hợp liên quan.
4. Viết contract test sớm, tích hợp những thay đổi nhỏ trong Sprint.
5. Dùng Daily Scrum để ưu tiên gỡ phụ thuộc và hoàn tất lát cắt.
6. Cho người dùng hoặc đại diện phù hợp thử Increment đã đạt DoD, đưa feedback vào Product Backlog.

### 19.4. Đánh giá có căn cứ

Sau vài Sprint, quan sát **PBI thực sự Done, cycle time, rework, lỗi nghiêm trọng, độ tin cậy test, phản hồi người dùng**. Không tuyên bố thành công chỉ vì số ticket tăng hoặc cuộc họp ngắn đi.

Nếu việc tái tổ chức trùng lúc có thêm nhân lực hoặc thay API đối tác, phải ghi **yếu tố gây nhiễu**, không tự quy toàn bộ kết quả cho một “nghi thức Scrum chuẩn”.

## 20. Trường hợp nghiên cứu B: “Board Kanban đẹp nhưng không giảm thời gian chờ”

### 20.1. Bối cảnh

Nhóm hỗ trợ tích hợp API có các cột To Do, Doing, Review, Done. Nhóm luôn kéo việc mới vào Doing khi có người rảnh; item cũ nằm chờ người duyệt contract và môi trường. Họ báo cáo “Kanban đang hoạt động vì mọi ticket được cập nhật”.

### 20.2. Số liệu minh họa

Một snapshot có bốn item đang mở:

| Item | Work item age | Trạng thái | Blocked duration ghi nhận | Tín hiệu |
| --- | ---: | --- | ---: | --- |
| A | 12 ngày | Chờ hợp đồng API | 6 ngày | Phụ thuộc quyết định |
| B | 9 ngày | Review | 2 ngày | Reviewer quá tải hoặc PR lớn |
| C | 4 ngày | Doing | 0 ngày | Cần kiểm tra còn tiến đều không |
| D | 2 ngày | Doing | 0 ngày | Mới bắt đầu |

**Age** là thời gian từ start point tới snapshot của item chưa Done. **Blocked duration** chỉ là phần thời gian thực item bị chặn theo chính sách ghi nhận, không tự phản ánh toàn bộ thời gian chờ bình thường.

### 20.3. Thử cải tiến

- Làm rõ khi nào item bắt đầu, Done và trạng thái chờ nào cần hiển thị.
- Đặt WIP limit thử nghiệm dựa trên thực tế, không sao chép một con số phổ quát.
- Khi Review đầy, ưu tiên swarm/review trước khi kéo việc mới.
- Ghi nguyên nhân blocked, người có quyền giải quyết và mốc xem lại.
- Tách dòng việc khẩn khỏi việc thường theo chính sách có trách nhiệm.
- Theo dõi aging WIP, throughput/cycle time và chất lượng để xem tác động.

### 20.4. Bài học

**Bảng Kanban không tự quản lý flow.** Việc đội **thay đổi cách ưu tiên, giảm WIP, giải quyết phụ thuộc và kiểm tra kết quả** mới tạo ra khả năng cải tiến.

## 21. Trường hợp nghiên cứu C: “Thay công cụ ba lần mà vẫn chậm”

### 21.1. Bối cảnh

Một nhóm chuyển từ bảng tính sang một phần mềm quản lý task, rồi sang công cụ khác có biểu đồ velocity và automation. Sau mỗi lần chuyển, tổ chức hy vọng sẽ có “quy trình Agile”. Nhưng:

- Nhu cầu người dùng vẫn được giao bằng một tài liệu dài ít ai làm rõ.
- API của đội khác vẫn phải chờ một người duy nhất trả lời.
- Test tích hợp chỉ chạy sau merge cuối Sprint.
- Người điều phối chỉ hỏi số task đóng, không xử lý dependency.
- Retrospective ghi nhiều action nhưng không có owner và điểm xem lại.

### 21.2. Chẩn đoán bằng cơ chế

Vấn đề không phải thiếu chức năng phần mềm. Các hàng chờ quan trọng do **quyền quyết định, cách chia công việc, thiếu integration test và thiếu vòng học hỏi**.

### 21.3. Cải tiến có thể thử trước khi mua công cụ tiếp

1. Lấy ba item gần đây và dựng **timeline từ yêu cầu tới Done**.
2. Phân loại thời gian làm chủ động, chờ API, chờ review, sửa lại và test.
3. Xác định ai có quyền chốt contract, ai hỗ trợ khi chuyên gia vắng.
4. Chọn một lát cắt nhỏ, viết AC và test rủi ro sớm.
5. Theo dõi các item chưa hoàn tất, đừng chỉ xem báo cáo đã Done.
6. Cải thiện workflow và chính sách trong công cụ hiện có trước khi quyết định thay.

### 21.4. Khi nào công cụ mới thật sự đáng cân nhắc?

Khi có bằng chứng công cụ hiện tại **không thể cung cấp khả năng cần thiết** như quản lý nhiều version contract, traceability theo chính sách hoặc bảo vệ dữ liệu, và việc thay có lợi ích thực so với chi phí học/chuyển đổi.

Không cần bài xích công cụ. Chỉ cần **tránh giao vai trò suy nghĩ và ra quyết định cho phần mềm**.

## 22. Scrum có thể kết hợp Kanban và XP mà không biến thành “mớ framework”

Một Scrum Team có thể:

- Giữ đúng **Sprint, trách nhiệm Scrum, Product Goal, Sprint Goal, Product Backlog, Sprint Backlog, Increment và DoD**.
- Dùng **Kanban visualization, WIP limits, work item age và cycle time** để nhìn flow và hỗ trợ hoàn tất PBI.
- Dùng **TDD, CI, refactoring, pairing hoặc contract tests** để nâng khả năng giao Increment chất lượng.
- Dùng **product discovery, prototype và phản hồi người dùng** để kiểm chứng giả thuyết giá trị.

### Một cách trình bày chính xác

> “Chúng tôi sử dụng Scrum cho trách nhiệm và chu kỳ kiểm tra–thích nghi sản phẩm; áp dụng các thực hành Kanban để cải thiện flow; dùng một số thực hành XP để tăng chất lượng kỹ thuật.”

Câu này rõ hơn:

> “Chúng tôi dùng ScrumbanXPDevOps, nên mọi phương pháp đều đã được áp dụng đầy đủ.”

### Nguyên tắc kết hợp

1. Nêu **vấn đề cần giải** trước khi chọn thực hành.
2. Giữ **tính nhất quán** với framework đang tuyên bố dùng.
3. Không nhân đôi sự kiện chỉ vì học thêm từ một phương pháp.
4. Không đặt các metric trái mục tiêu, ví dụ thưởng số task mới khi đã giới hạn WIP.
5. Kiểm tra tác động tới **DoD, chất lượng, feedback và bền vững**.

Không có nghĩa framework càng nhiều thì càng tốt. **Ít thực hành nhưng có tác dụng và được hiểu rõ** thường đáng tin hơn một bộ thuật ngữ đồ sộ.

## 23. Tiêu chí chọn cách phối hợp theo bối cảnh

Đừng hỏi “Scrum hay Kanban cái nào tốt hơn?” như một cuộc thi. Hãy hỏi **vấn đề và điều kiện của nhóm**.

### Bảy chiều đánh giá

| Chiều | Câu hỏi cần hỏi | Hệ quả đối với lựa chọn |
| --- | --- | --- |
| **Dạng công việc** | Phát triển sản phẩm có mục tiêu hay yêu cầu đến liên tục? | Nhịp Sprint hoặc flow-first có thể phù hợp khác nhau |
| **Độ bất định** | Giá trị/giải pháp đã biết hay cần nhiều vòng khám phá? | Cần feedback nhanh, slicing, spike hoặc discovery |
| **Mức độ khẩn** | Có sự cố không thể hoãn? | Chính sách expedite và quyền ứng phó rõ |
| **Phụ thuộc** | Nhóm tự tích hợp được hay phải chờ nhiều bên? | Hợp đồng, điều phối, blocked visibility và review năng lực |
| **Chất lượng** | Độ rủi ro dữ liệu, vận hành và mức sẵn có của test? | DoD/quality policy, CI, XP practices |
| **Người nhận giá trị** | Có thể nhận feedback thường xuyên từ ai? | Sprint Review, demo, usability test hoặc phản hồi dịch vụ |
| **Quyền quyết định** | Ai được ưu tiên, điều chỉnh phạm vi và xử lý rủi ro? | Tránh chọn framework khi tổ chức chưa trao trách nhiệm cần thiết |

### Khung thảo luận có điều kiện

| Quan sát | Hướng có thể cân nhắc | Điều cần tránh |
| --- | --- | --- |
| Một sản phẩm phức tạp, có Product Goal và nhu cầu kiểm tra kết quả theo nhịp | Scrum đầy đủ nếu các trách nhiệm và Increment có thể thực hiện | Dùng Sprint để chứa pha lớn không tạo DoD |
| Yêu cầu hỗ trợ liên tục, thứ tự thường đổi theo mức khẩn | Kanban flow-first với service policies | Trì hoãn sự cố chỉ để giữ Sprint plan |
| Chất lượng thấp, lỗi tích hợp và rework nhiều | TDD/CI/contract test, pairing hoặc refactoring theo rủi ro | Mua dashboard mới trước khi sửa feedback kỹ thuật |
| Backlog lớn nhưng chưa rõ người dùng cần gì | Product discovery, user story mapping, giả thuyết và thử nghiệm | Ước lượng mọi ticket thay vì kiểm chứng nhu cầu |
| Nhiều đội bị chặn chờ hợp đồng API | Quản lý phụ thuộc, hợp đồng nhỏ và tích hợp thường xuyên | Thêm hội đồng status không có quyền quyết định |

Các hướng này có thể kết hợp; lựa chọn cuối cùng cần tôn trọng **ràng buộc pháp lý, chất lượng và trách nhiệm của sản phẩm**.

## 24. Quy trình chẩn đoán trước khi thay framework hoặc công cụ

Thay vì mua phần mềm hoặc đổi tên nhóm, hãy thực hiện một vòng chẩn đoán ngắn.

### Bước 1 – Xác định vấn đề có nghĩa

Ví dụ không đủ rõ: “Nhóm chưa Agile.”

Ví dụ có thể kiểm tra: “Những story liên quan API mất nhiều ngày chờ review và không có Increment dùng được cuối Sprint.”

### Bước 2 – Xác định người dùng, giá trị và chất lượng

Ai cần kết quả? Những điều kiện nào cho phép gọi phần mềm dùng được? DoD hoặc chính sách chất lượng nào đang áp dụng?

### Bước 3 – Xem ba item thực, không chỉ biểu đồ tổng hợp

Với mỗi item, dựng từ lúc yêu cầu đến khi Done/snapshot:

- Khi nào bắt đầu?
- Đã ở trạng thái nào, chờ ai và vì sao?
- Có rework không, nguyên nhân gì?
- Kiểm thử/feedback xuất hiện lúc nào?
- Người nào có quyền thay đổi ưu tiên hoặc giải quyết dependency?

### Bước 4 – Đặt giả thuyết về cơ chế

Ví dụ “Việc chờ Review lâu có thể do PR lớn, thiếu reviewer dự phòng hoặc WIP quá nhiều”, không dừng ở “đội thiếu kỷ luật”.

### Bước 5 – Thử một thay đổi nhỏ

Có thể thử PR nhỏ hơn, giới hạn WIP, review chéo, làm rõ AC, contract test hoặc mời người dùng thử Increment sớm.

### Bước 6 – Bảo vệ guardrail

Không hạ DoD, bỏ test phân quyền, ép overtime hoặc che item già để dashboard đẹp. Giữ quyền và nghĩa vụ tổ chức.

### Bước 7 – Đo và phản hồi

Xem flow, chất lượng, outcome cùng phản hồi thành viên; kiểm tra yếu tố khác cùng thay đổi. Giữ, điều chỉnh hoặc bỏ giả thuyết theo bằng chứng.

### Sơ đồ chu trình

~~~mermaid
flowchart TD
    A["Vấn đề thật của sản phẩm/nhóm"] --> B["Bằng chứng từ item và người dùng"]
    B --> C["Giả thuyết về nguyên nhân hệ thống"]
    C --> D["Chọn thực hành/khung phù hợp"]
    D --> E["Thử nhỏ và bảo vệ DoD"]
    E --> F["Quan sát flow + quality + outcome"]
    F --> G{"Tín hiệu có ích và an toàn?"}
    G -- "Có" --> H["Giữ/điều chỉnh, chia sẻ điều kiện áp dụng"]
    G -- "Chưa" --> I["Sửa giả thuyết hoặc dừng thử"]
    H --> A
    I --> A
~~~

## 25. Đo “Agile có tác dụng không” bằng gì?

Không có **một điểm số Agile phổ quát** chứng minh một nhóm tốt hơn nhóm khác. Các tín hiệu nên giúp đội ra quyết định về **khả năng giao giá trị, phản hồi, chất lượng và nhịp làm việc bền vững**.

### Một bảng đo lường cân bằng

| Chiều | Tín hiệu tham khảo | Giúp trả lời | Giới hạn |
| --- | --- | --- | --- |
| **Giá trị người dùng** | Task success, mức sử dụng tính năng, phản hồi định tính | Increment có giải quyết nhu cầu không? | Event tracking sai hoặc mẫu người dùng lệch |
| **Phần mềm hoạt động** | Increment/PBI đạt DoD, kiểm chứng hành vi với người dùng | Thay đổi đã sử dụng được hay chỉ code xong? | Số lượng không phản ánh độ lớn và tác động |
| **Dòng công việc** | Throughput, cycle time, WIP, work item age | Việc đi tới Done ổn định không? | Phụ thuộc start/finish và loại item |
| **Thời gian chờ** | Blocked time, aging WIP, thời gian ở Review/Test | Hệ thống nghẽn ở đâu? | Không phải mọi chờ đều được đánh dấu blocked |
| **Làm lại/chất lượng** | Rework do lỗi, reopened, lỗi production, test stability | Có phát hiện sai sớm và giao an toàn? | Nhiều lỗi được phát hiện sớm có thể phản ánh test tốt hơn |
| **Phản hồi và học hỏi** | Thời gian từ giả thuyết tới kiểm chứng, kết quả thử nghiệm | Đội có học điều mới và thay đổi quyết định? | Số workshop hoặc lượt demo không chứng minh học hỏi |
| **Bền vững** | Overtime, sự cố lặp, phụ thuộc một chuyên gia | Cách làm có duy trì lâu dài không? | Khảo sát và dữ liệu cần bảo vệ sự riêng tư |

### Một ví dụ tính cycle time và throughput

Giả sử năm hạng mục cùng loại đã Done trong một khoảng quan sát, với cycle time theo ngày lịch:

~~~text
3, 4, 5, 8, 12 ngày
~~~

- **Throughput của khoảng quan sát:** 5 item Done, không phải “5 item/ngày”.
- **Cycle time trung vị:** 5 ngày.
- **Cycle time trung bình:** (3 + 4 + 5 + 8 + 12) / 5 = 6,4 ngày.
- **Khoảng dao động quan sát:** 3 đến 12 ngày.

Nếu có ba item đang mở với age 2, 9 và 14 ngày, **không đưa các age này vào mẫu cycle time đã Done như thể đã hoàn thành**. Tuy nhiên, item 14 ngày đang mở có thể rất quan trọng để đội điều tra rủi ro ngay.

**Cỡ mẫu chỉ năm item không đủ để dự báo tin cậy**. Cần xem thời kỳ đủ phù hợp, loại item, số việc đang mở và khả năng thay đổi workflow.

### Đừng biến chỉ số thành mục tiêu tự thân

Nếu thưởng theo throughput, đội có thể chia ticket nhỏ hơn nhưng không giao thêm giá trị. Nếu thưởng theo cycle time ngắn, đội có thể dừng tính thời gian trong lúc bị chặn. Nếu thưởng theo velocity, điểm ước lượng có thể phình to.

Đây là lý do cần **giữ cách đo nhất quán, kiểm tra dữ liệu và xem nhiều guardrail cùng lúc**, thay vì dùng một KPI để kết luận “mức độ Agile”.

## 26. Một chương trình thử nghiệm trong bốn tuần

Một nhóm đang tự gọi là “Scrum team”, nhưng không giao được Increment tích hợp và có rất nhiều story chờ Review. Thay vì tổ chức một buổi đào tạo thuật ngữ rồi tuyên bố hoàn tất chuyển đổi, nhóm có thể thử cải tiến nhỏ.

### Tuần 1 – Quan sát và đặt vấn đề

- Làm rõ Product Goal hoặc kết quả người dùng đang hướng tới.
- Xem ba tới năm item thực từ lúc bắt đầu tới hiện tại/Done.
- Ghi nguồn chờ, rework, test tích hợp và khi nào người dùng có thể thử.
- Đối chiếu các phần Scrum đang được dùng với **mục đích** của chúng.
- Ghi baseline thích hợp: WIP, aging item, cycle time, số PBI đạt DoD, chất lượng và feedback.

**Đầu ra:** Một vấn đề cụ thể, ví dụ “Review và tích hợp đến quá muộn để tạo Increment trong Sprint”.

### Tuần 2 – Chọn giả thuyết và can thiệp

Giả thuyết:

> “Nếu mỗi Sprint tập trung một lát cắt người dùng có Sprint Goal rõ, chia việc nhỏ, kéo kiểm thử/tích hợp lên sớm và giới hạn WIP ở Review, đội có thể giao Increment đạt DoD thường xuyên hơn mà không tăng lỗi.”

Can thiệp:

- Product Owner và Developers làm rõ một Sprint Goal có ý nghĩa.
- Cùng chốt AC và DoD để không gọi “code xong” là Done.
- Viết contract/integration tests cho ranh giới thường sai.
- Khi Review quá tải, ưu tiên giúp hoàn tất thay vì kéo thêm việc mới.
- Dùng Sprint Review để nhận phản hồi thực về Increment, không chỉ trình chiếu tình trạng ticket.

### Tuần 3 – Quan sát và phản hồi

- Xem item nào đã Done thật, item nào già và phụ thuộc gì.
- Tìm nguyên nhân nếu pipeline đỏ hoặc test flaky.
- Thu feedback định tính từ developers, tester, Product Owner và stakeholders.
- Giữ test phân quyền, tính đúng dữ liệu, DoD và nhịp bền vững.
- Điều chỉnh khi rủi ro nghiêm trọng xuất hiện; không chờ hết kỳ mới sửa.

### Tuần 4 – Đánh giá và lựa chọn tiếp

| Câu hỏi | Bằng chứng cần xem |
| --- | --- |
| Sprint Goal đã hỗ trợ ưu tiên chưa? | Những quyết định đổi thứ tự/giảm phạm vi có lý do |
| Có Increment đạt DoD và người dùng thử được chưa? | Demo hành vi thực, test, feedback |
| Flow có dễ dự báo hơn không? | Cycle time, WIP, aging item và throughput theo loại việc |
| Có đánh đổi chất lượng không? | Lỗi nghiêm trọng, rework, test stability, incident |
| Nhóm có đủ quyền thích nghi? | Cách xử lý blocker và quyết định Product Backlog |
| Có điều gì không phù hợp Scrum? | Loại việc, ưu tiên khẩn, khả năng hình thành mục tiêu Sprint |

**Kết luận có trách nhiệm:** “Có tín hiệu cải thiện trong kỳ quan sát; chưa chắc toàn bộ do một can thiệp vì đã thay đổi cả test và cách chia item”. Giữ, chỉnh, dừng hoặc chuyển hướng theo bằng chứng.

### Guardrail của thử nghiệm

- Không hạ Definition of Done để tăng số item Done.
- Không đưa dữ liệu học viên ra ngoài quyền khi thử tính năng.
- Không ép overtime để đạt velocity.
- Không xóa item già hoặc đổi mốc start/finish để tạo dashboard đẹp.
- Không dùng thử nghiệm làm công cụ xếp hạng cá nhân.

## 27. Một workshop ngắn phân biệt giá trị, framework và công cụ

Workshop này giúp đội nhìn ra **một nghi thức đang phục vụ giá trị gì**, thay vì chỉ học thuộc tên phương pháp.

### Chuẩn bị

Chọn một thay đổi thật, ví dụ “Học viên tiếp tục đúng bài gần nhất còn quyền”. Có Product Owner/đầu mối nghiệp vụ, developer, tester và người liên quan đủ để hiểu rủi ro.

### Phần A – Phân loại thẻ

Cho các thẻ:

~~~text
1. Phản hồi sớm từ người dùng
2. Sprint Goal
3. Cột Review trong Jira
4. Continuous Integration
5. Product Backlog
6. Giới hạn WIP
7. TDD
8. Sprint Retrospective
9. Kiểm tra quyền ở API
10. Đếm số ticket mỗi developer
~~~

**Yêu cầu:** Phân loại theo:

- Giá trị/nguyên tắc.
- Thành phần framework cụ thể.
- Thực hành kỹ thuật/flow.
- Công cụ hoặc cấu hình công cụ.
- Chỉ số/hành vi có thể gây tác dụng phụ.

### Phần B – Truy vết cơ chế

Với mỗi thẻ, hỏi:

1. Nó giải quyết **vấn đề gì**?
2. Điều gì xảy ra nếu thực hiện theo hình thức nhưng không đạt mục đích?
3. Cần bằng chứng gì để biết hoạt động có tác dụng?
4. Bối cảnh nào khiến cách làm cần đổi?
5. Có ràng buộc chất lượng hoặc quyền nào phải giữ?

### Phần C – Chọn một thử nghiệm

Nhóm chọn **một điểm nghẽn thật** (ví dụ Review chậm) và chỉ thiết kế **một can thiệp nhỏ**. Đầu ra là giả thuyết, người phối hợp, dữ liệu cần xem, guardrail và mốc xem lại.

### Ví dụ kết quả phân loại

| Thẻ | Cách hiểu đúng |
| --- | --- |
| Phản hồi sớm từ người dùng | Nguyên tắc/hành vi phù hợp tinh thần Agile |
| Sprint Goal | Cam kết của Sprint Backlog trong Scrum |
| Cột Review trong Jira | Cấu hình công cụ thể hiện một phần workflow |
| Continuous Integration | Thực hành kỹ thuật giúp nhận feedback sớm |
| Product Backlog | Tạo tác Scrum |
| WIP limit | Chính sách quản lý flow, thường gắn với Kanban |
| TDD | Thực hành kỹ thuật, thường nhắc tới trong XP |
| Sprint Retrospective | Sự kiện Scrum có mục tiêu cải tiến |
| Kiểm tra quyền ở API | Kiểm soát chất lượng/an toàn theo rủi ro |
| Đếm ticket/developer | Hoạt động đo có nguy cơ bị lạm dụng làm KPI cá nhân |

## 28. Bảng nhận diện những ngộ nhận phổ biến

| Câu nói sai lệch | Vì sao chưa đúng | Cách hiểu/ứng xử phù hợp |
| --- | --- | --- |
| **“Agile = Scrum.”** | Scrum là một framework trong hệ cách làm thích nghi rộng hơn | Chọn Scrum khi phù hợp; Agile không bắt buộc mọi đội Scrum |
| **“Dùng Jira = Agile.”** | Công cụ không quyết định quyền, feedback hoặc chất lượng | Đánh giá hành vi và kết quả |
| **“Có Daily 15 phút là đã Scrum.”** | Một sự kiện không thay cả framework | Hiểu mục đích, trách nhiệm, tạo tác và cam kết |
| **“Scrum = họp nhiều.”** | Sự kiện được thiết kế tạo cơ hội kiểm tra/thích nghi | Sửa những buổi chỉ đọc status |
| **“Product Owner chỉ cần nhập ticket.”** | PO chịu trách nhiệm giá trị và Product Backlog | Trao quyền và trách nhiệm đúng nghĩa |
| **“Scrum Master quản lý tiến độ mọi người.”** | SM không phải cảnh sát điểm số | Hỗ trợ hiệu quả Scrum Team và tháo trở ngại |
| **“Sprint bắt buộc khóa cứng mọi công việc.”** | Sprint Backlog được thích nghi khi học điều mới | Giữ Sprint Goal, điều chỉnh kế hoạch phù hợp |
| **“Cứ code merge là Done.”** | Increment phải đạt DoD và dùng được | Tích hợp, kiểm chứng chất lượng chung |
| **“Sprint Review là lúc được phép release.”** | Review không phải cổng phát hành của Scrum | Phân biệt DoD và release policy |
| **“Kanban là board ba cột.”** | Board chưa đủ quản lý flow | Minh bạch workflow/WIP/chính sách/feedback |
| **“Không có Sprint thì không Agile.”** | Kanban/flow-first có thể phù hợp | Chọn cơ chế theo công việc và phản hồi |
| **“XP chỉ dành cho người code cực nhanh.”** | XP chú trọng thực hành kỹ thuật và phản hồi | Dùng TDD, CI, pairing, refactoring theo rủi ro |
| **“Story point = giờ công.”** | Point là quy ước ước lượng tương đối của đội nếu dùng | Không tự quy đổi hay dùng thưởng phạt |
| **“Velocity tăng là giá trị tăng.”** | Điểm có thể phình, loại item đổi | Xem Done thật, quality, outcome |
| **“Mọi đội nên có cùng WIP limit.”** | Năng lực và loại việc khác nhau | Thử mức phù hợp, quản lý ngoại lệ |
| **“Agile không cần tài liệu.”** | Tài liệu có giá trị khi hỗ trợ chất lượng, phối hợp và nghĩa vụ | Viết đúng mức, đúng người sử dụng |
| **“Agile không cần kế hoạch.”** | Cần định hướng và dự báo, nhưng có thích nghi | Rolling-wave planning và feedback |
| **“Thay đổi lúc nào cũng tốt.”** | Mọi thay đổi đều có chi phí và rủi ro | Điều chỉnh có chủ đích, giữ chất lượng và trách nhiệm |
| **“Mọi team phải cùng framework.”** | Loại công việc và điều kiện khác nhau | Thống nhất guardrail, tùy biến phương pháp |
| **“Càng nhiều ceremony càng trưởng thành.”** | Nghi thức không tạo giá trị nếu không có quyết định | Giữ vòng phản hồi có tác dụng |
| **“Retro chỉ cần nêu ra vấn đề.”** | Cải tiến cần thay đổi và kiểm chứng | Action nhỏ, owner, kỳ xem lại |
| **“Framework sẽ sửa được mọi vấn đề kỹ thuật.”** | Test, CI, thiết kế và chất lượng vẫn cần thực hành cụ thể | Đầu tư vào kỹ thuật tốt và phản hồi sớm |
| **“Chỉ nhóm phát triển chịu trách nhiệm Agile.”** | Giá trị phụ thuộc người sản phẩm, vận hành và tổ chức | Làm rõ quyền, phối hợp và feedback xuyên ranh giới |
| **“Agile cho phép bỏ bảo mật để nhanh.”** | Tốc độ không thay nghĩa vụ an toàn | Giữ DoD, quyền và kiểm chứng theo rủi ro |

## 29. Bài tập thực hành

### Bài tập 1 – Phân tầng các thuật ngữ

Cho danh sách: Agile Manifesto, Scrum, Kanban WIP limit, XP, TDD, Sprint Goal, Jira, GitHub Issues, CI, Product Goal, cycle time, usability test.

**Yêu cầu:** Chia thành giá trị/nguyên tắc, framework, cam kết/tạo tác, thực hành, công cụ và chỉ số/bằng chứng. Giải thích ba trường hợp thuộc nhiều lớp hoặc có ý nghĩa tùy bối cảnh.

### Bài tập 2 – Một nhóm “đã Agile”?

Một nhóm dùng Jira, Sprint 2 tuần và Daily 15 phút. Mọi yêu cầu vẫn được khóa đầu quý; không có Increment đạt DoD cho tới cuối quý.

**Yêu cầu:** Nêu ít nhất bốn thiếu hụt trong khả năng phản hồi, trách nhiệm và chất lượng; đề xuất hai thay đổi nhỏ trước khi mua công cụ khác.

**Gợi ý:** Đặt câu hỏi về Product Goal, PBI thực sự Done và feedback người dùng.

### Bài tập 3 – Daily Scrum hay status meeting?

Trưởng nhóm gọi lần lượt từng developer báo cáo hôm qua/hôm nay, ghi ai chưa cập nhật ticket rồi kết thúc. Không ai trao đổi Sprint Goal hoặc cách gỡ blocker.

**Yêu cầu:** Viết lại mục đích và một agenda 15 phút để Developers kiểm tra tiến triển hướng Sprint Goal và điều chỉnh kế hoạch.

### Bài tập 4 – Product Owner có thực sự chịu trách nhiệm giá trị?

Một người có chức danh Product Owner nhưng không được quyết định thứ tự backlog, không thể trao đổi với người dùng và chỉ nhập yêu cầu của quản lý.

**Yêu cầu:** Giải thích trách nhiệm bị thiếu, hậu quả đối với Product Goal và đề xuất cách thiết lập quyền quyết định không vượt các ràng buộc tổ chức.

### Bài tập 5 – Kiểm tra Scrum theo các thành phần chính

Một nhóm dùng Sprint Planning, Daily Scrum và một board. Họ không có Sprint Goal, không có Sprint Review, không có DoD và Product Backlog không có định hướng giá trị.

**Yêu cầu:** Liệt kê những trách nhiệm/sự kiện/tạo tác/cam kết chưa được thực hành, giải thích tác động và đề xuất con đường dùng Scrum đầy đủ hoặc chọn cách tổ chức khác phù hợp.

### Bài tập 6 – Scrumfall

Một dự án chia: Sprint 1 phân tích, Sprint 2 thiết kế, Sprint 3 UI, Sprint 4 API, Sprint 5 test và Sprint 6 tích hợp.

**Yêu cầu:** Giải thích vì sao chỉ đổi tên giai đoạn chưa tạo feedback Agile. Chia chức năng “Tiếp tục học” thành ba lát cắt tích hợp có thể kiểm chứng và bảo vệ quyền dữ liệu.

### Bài tập 7 – Có board Kanban là đủ?

Một đội có To Do/Doing/Done. WIP không giới hạn, item chờ Review bị treo nhiều tuần nhưng mỗi người tiếp tục kéo task mới.

**Yêu cầu:** Đề xuất workflow/chính sách WIP/aging review, ba câu hỏi của buổi flow review và hai tín hiệu chất lượng cần giữ.

### Bài tập 8 – Chẩn đoán metric sai

Đội A đạt velocity 40 point, đội B đạt 22 point; trưởng bộ phận muốn đánh giá A “gần gấp đôi năng suất”.

**Yêu cầu:** Giải thích ít nhất năm lý do so sánh không hợp lệ; đề xuất bộ bằng chứng thay thế để xem từng đội có cải tiến thật không.

### Bài tập 9 – Ước lượng có cần story point?

Đội vận hành có yêu cầu đến liên tục, nhiều ticket nhỏ và sự cố khẩn; họ muốn thử dự báo theo throughput thay vì point.

**Yêu cầu:** Đề xuất cách định nghĩa item, start/finish, phân nhóm dịch vụ, chọn kỳ dữ liệu và báo bất định. Giải thích vì sao không dùng điểm không có nghĩa “không Agile”.

### Bài tập 10 – Kết hợp Scrum/Kanban/XP

Một Scrum Team đã có Product Goal, Sprint Goal, DoD và Increment nhưng thường bị chặn ở Review và lỗi tích hợp.

**Yêu cầu:** Chọn hai thực hành Kanban và hai thực hành XP có thể bổ sung; ghi giả thuyết cơ chế, metric và guardrail. Giải thích vì sao không cần tạo thêm sự kiện Scrum bắt buộc.

### Bài tập 11 – Vì sao mua công cụ mới chưa chắc hữu ích?

Một công ty đã chuyển công cụ quản lý task ba lần, nhưng các nhóm vẫn đợi một người chốt API, thiếu integration test và không dùng phản hồi người học.

**Yêu cầu:** Nêu nguyên nhân hệ thống, một thí nghiệm nhỏ và dấu hiệu nào mới cho thấy cần thay công cụ thật.

### Bài tập 12 – Phân biệt output với outcome

Trong Sprint, một đội hoàn thành 16 PBI đạt DoD và release tính năng “Tiếp tục học” cho nhóm người dùng được phép. Tuy nhiên rất ít người sử dụng.

**Yêu cầu:** Đề xuất hai nguồn phản hồi định tính và hai chỉ số định lượng có mẫu số rõ; phân biệt chất lượng/hoàn tất với giá trị và bảo vệ quyền riêng tư.

### Bài tập 13 – Chọn framework cho ba nhóm

Có nhóm phát triển tính năng, nhóm hỗ trợ sự cố 24/7 và nhóm tích hợp đối tác cần contract reviews. Công ty yêu cầu tất cả dùng Sprint hai tuần và cùng số story point.

**Yêu cầu:** Lập ma trận loại việc, phụ thuộc, mức khẩn, rủi ro, cơ chế phối hợp và tiêu chuẩn chất lượng chung; đề xuất cách thử điều chỉnh không bỏ nghĩa vụ.

### Bài tập 14 – Đọc dữ liệu flow

Năm item Done có cycle time theo ngày **3, 4, 5, 8, 12**; ba item đang mở có age **2, 9, 14**.

**Yêu cầu:** Tính throughput của kỳ quan sát, median và mean cycle time; chỉ ra item đang mở nào cần điều tra trước và giải thích vì sao không được nhập age vào phân bố cycle time đã Done.

**Gợi ý đáp án:** Throughput **5 item trong kỳ**, median **5 ngày**, mean **6,4 ngày**; item age 14 là tín hiệu cần điều tra theo mức rủi ro và bối cảnh, không tự kết luận cá nhân làm chậm.

### Bài tập 15 – Thiết kế thử nghiệm có guardrail

Một đội muốn bỏ review code để “Agile nhanh hơn”. Họ đang có nhiều PR lớn và thiếu reviewer.

**Yêu cầu:** Xác định mục tiêu kiểm soát mà review đang bảo vệ, nguyên nhân chờ có thể có và hai thay đổi an toàn hơn. Đo hiệu quả cùng lỗi sản phẩm, rework và chất lượng.

### Bài tập 16 – Viết lời giải thích cho stakeholders

Một lãnh đạo nói: “Hãy triển khai Jira và đào tạo Scrum một tuần, sau đó toàn tổ chức phải Agile.”

**Yêu cầu:** Viết bản giải thích 180–250 từ với cấu trúc:

1. Công cụ và đào tạo có thể hỗ trợ điều gì.
2. Vì sao thay đổi hành vi/trách nhiệm/feedback mới quan trọng.
3. Hai giả thuyết cải tiến nên thử trong một bối cảnh cụ thể.
4. Guardrail chất lượng và phép đo kết quả.
5. Khi nào nên xem lại quyết định tiếp theo.

### Bài tập 17 – Phân tích phản hồi trái chiều

Đội thử giới hạn WIP và tăng CI. Trong bốn tuần, cycle time giảm nhưng lỗi production không giảm; cùng lúc đối tác sửa API và loại item cũng thay đổi.

**Yêu cầu:** Viết nhận định gồm điều quan sát được, điều chưa chứng minh, yếu tố gây nhiễu, kiểm tra cần thêm và một quyết định thận trọng.

## 30. Checklist nhận diện Agile thực chất

Trước khi tuyên bố một nhóm “đã chuyển sang Agile”, hãy kiểm tra:

- [ ] Có **mục tiêu sản phẩm hoặc dịch vụ** rõ hơn việc đạt đủ số ticket không?
- [ ] Người nhận giá trị và nguồn phản hồi được xác định?
- [ ] Đã hiểu **Agile là giá trị/nguyên tắc**, không đồng nghĩa một framework cụ thể?
- [ ] Nếu chọn Scrum, các **trách nhiệm, sự kiện, tạo tác và cam kết** được hiểu đúng?
- [ ] Product Owner có quyền và trách nhiệm về giá trị và Product Backlog trong phạm vi Scrum?
- [ ] Scrum Master được dùng để hỗ trợ hiệu quả, không trở thành người kiểm điểm cá nhân?
- [ ] Developers có trách nhiệm lập và thích nghi kế hoạch nhằm tạo Increment chất lượng?
- [ ] Sprint Goal có ý nghĩa hoặc đội đang dùng cách điều phối khác có lý do rõ?
- [ ] Daily Scrum giúp kiểm tra tiến triển hướng mục tiêu, không chỉ đọc status?
- [ ] Sprint Review có kiểm tra Increment và tạo phản hồi thay vì chỉ là lễ phê duyệt?
- [ ] Retrospective có thử nghiệm và xem lại hành động cải tiến?
- [ ] Product Backlog được sắp thứ tự theo giá trị/rủi ro và phát triển dần?
- [ ] **Definition of Done** được bảo vệ, không bị giảm để làm đẹp tỷ lệ Done?
- [ ] Nếu nhiều Scrum Team cùng sản phẩm, có **DoD chung** và phối hợp Increment?
- [ ] Các lát cắt nhỏ thực sự được tích hợp, không dồn “Sprint tích hợp” cuối?
- [ ] Nếu dùng Kanban, đã minh bạch workflow/WIP/chính sách và theo dõi flow?
- [ ] Có chính sách xử lý blocker và item đang già, không chỉ kéo thêm việc mới?
- [ ] Có thực hành kỹ thuật tương xứng rủi ro như CI, test, review hoặc pairing?
- [ ] Công cụ đang hỗ trợ quyết định và cộng tác, không chỉ tăng số trường báo cáo?
- [ ] Có phân biệt **merge, Done, deployment, release và outcome**?
- [ ] Story point/velocity không bị dùng để xếp hạng năng suất cá nhân hoặc các đội?
- [ ] Các chỉ số flow có start/finish, loại item, kỳ đo và giới hạn rõ?
- [ ] Có xem cả work item age đang mở và lỗi chất lượng, không chỉ ticket đã đóng?
- [ ] Lỗi nghiêm trọng, quyền riêng tư và nghĩa vụ tổ chức không bị bỏ để “nhanh hơn”?
- [ ] Cách chọn framework phản ánh loại công việc, mức khẩn, phụ thuộc và bất định?
- [ ] Phần tiêu chuẩn chung và phần đội được tự quyết được phân biệt?
- [ ] Có thời gian nhận phản hồi người dùng đủ sớm để điều chỉnh Product Backlog?
- [ ] Cải tiến được xem như giả thuyết cần kiểm chứng, không phải nghi thức bắt buộc vì hình thức?
- [ ] Đã ghi nguồn gây nhiễu và độ bất định khi kết luận trước/sau?
- [ ] Cách làm giữ nhịp làm việc bền vững, không lấy overtime làm “Agile velocity”?
- [ ] Bài học được chia sẻ cùng bối cảnh để đội khác thích nghi thay vì sao chép?

Checklist không phải thước đo phần trăm “maturity Agile”. Dùng nó để **tìm một vài quyết định quan trọng cần cải thiện**, không tạo thêm một bộ chứng chỉ hoặc quy trình chấm điểm.

## 31. Tổng kết

- **Agile không đồng nghĩa Scrum.** Agile nêu giá trị và nguyên tắc về hợp tác, phần mềm hoạt động, phản hồi và thích nghi; Scrum là framework cụ thể giúp thực nghiệm và giao Increment trong điều kiện phù hợp.
- **Scrum không chỉ là Sprint và Daily Scrum.** Trách nhiệm giải trình, năm sự kiện, ba tạo tác và ba cam kết có mục đích gắn với nhau. Nếu chọn Scrum, cần hiểu và thực hành cấu trúc đó, không chỉ đổi tên các cuộc họp cũ.
- **Kanban không chỉ là board.** Minh bạch workflow, giới hạn WIP, quản lý flow, chính sách và vòng phản hồi mới giúp đội nhìn ra điểm nghẽn và cải tiến.
- **XP không chỉ là code nhanh.** TDD, pairing, CI, refactoring và các thực hành kỹ thuật giúp nhóm nhận phản hồi sớm, bảo vệ chất lượng và thay đổi an toàn.
- **Công cụ là phương tiện, không phải chứng chỉ Agile.** Một bảng giấy có thể hỗ trợ nhóm tốt; một công cụ lớn cũng có thể chỉ số hóa những hàng đợi và thói quen cũ.
- **Không có một công thức cho mọi đội.** Nhóm phát triển tính năng, vận hành sự cố và tích hợp đối tác có thể cần nhịp phối hợp khác nhau trong cùng các tiêu chuẩn chất lượng bắt buộc.
- **Đo giá trị, chất lượng và dòng việc thay vì chỉ đếm hoạt động.** Story point, velocity, số merge, số cuộc họp hoặc số ticket chỉ hữu ích khi đặt đúng câu hỏi, không dùng để quy trách nhiệm cá nhân.
- **Một chuyển đổi có nghĩa là thay đổi hành vi và quyền quyết định.** Làm rõ Product Goal, giao lát cắt đạt DoD, nhận feedback, giải quyết blocker và thử cải tiến dựa trên bằng chứng đáng tin.

**Câu hỏi quan trọng nhất không phải “Chúng ta đã triển khai Scrum hoặc công cụ nào?”, mà là: “Cách làm hiện tại có giúp chúng ta giao giá trị an toàn sớm hơn, học được điều mới và điều chỉnh quyết định tốt hơn không?”**
