# Duy trì minh bạch mục tiêu, công việc và quyết định

Ba nhóm đang phát triển một nền tảng học lập trình Java: Product Owner và một phần Developers ở Việt Nam, những người phát triển khác ở châu Âu, bộ phận kiểm thử và vận hành có người ở Bắc Mỹ. Thứ Hai, PO thông báo “ưu tiên Học tiếp” trong một cuộc gọi. Thứ Ba, nhóm API hoàn thành mã nhưng chưa kiểm thử tích hợp. Thứ Tư, quy tắc lưu tiến độ được thay trong cuộc họp không ghi kết luận. Thứ Năm, nhóm giao diện tiếp tục xây theo quy tắc cũ, bảng công việc vẫn hiển thị nhiều mục “đang làm”, còn quản lý tưởng có thể phát hành ngay.

Vấn đề không nhất thiết là các thành viên thiếu nỗ lực. Vấn đề là **mục tiêu, công việc và quyết định không còn tạo thành hiểu biết chung**. Những thông tin tưởng như “ai cũng biết” trong một văn phòng có thể trở thành các giả định mâu thuẫn khi nhóm không cùng địa điểm hoặc múi giờ.

Một nhóm phân tán hiệu quả không cần giám sát ai đang trực tuyến từng phút. Họ cần thông tin đủ rõ để mỗi người, dù bắt đầu ngày làm việc sau đồng đội nhiều giờ, có thể trả lời:

- **Vì sao chúng ta làm việc này?** Kết quả người dùng và ưu tiên hiện tại là gì?
- **Điều gì đang xảy ra?** PBI nào đạt Done, mục nào đang chờ, rủi ro nào chưa xử lý?
- **Quyết định nào có hiệu lực?** Ai quyết, vì sao, từ khi nào và với phạm vi nào?
- **Ai cần hành động tiếp?** Phụ thuộc nào chờ ai, bao giờ cần phản hồi hoặc chuyển cấp?
- **Chúng ta đã học được gì?** Phần mềm đã đưa đến người dùng nào, có phản hồi gì và cần điều chỉnh gì?

Bài **“Duy trì minh bạch mục tiêu, công việc và quyết định”** thuộc chương **Nhóm phân tán** trong module **AGILE_DEVELOPMENT**. Module hướng tới hiểu các giá trị, nguyên tắc Agile thông qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và các số đo dòng công việc. Trong bối cảnh phân tán, minh bạch là **năng lực giúp những thực hành này hoạt động**, chứ không phải bộ biểu mẫu bổ sung để quản lý sự hiện diện.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **minh bạch phục vụ quyết định và phối hợp** với báo cáo hình thức hoặc giám sát cá nhân.
2. Thiết kế thông tin rõ ràng cho ba lớp: **mục tiêu, trạng thái công việc, quyết định**.
3. Diễn đạt Product Goal và Sprint Goal bằng kết quả có thể kiểm tra, không chỉ bằng số ticket hoặc story points.
4. Thiết kế board/Definition of Workflow thể hiện WIP, blocked, phụ thuộc, người thực hiện hành động tiếp và bằng chứng Done.
5. Phân biệt vai trò của Product Backlog, Sprint Backlog, Definition of Done và báo cáo release.
6. Viết quyết định dạng **decision log/ADR/RFC** với bối cảnh, người có thẩm quyền, phương án, hệ quả và điều kiện xem lại.
7. Lựa chọn giao tiếp **bất đồng bộ hoặc đồng bộ** theo rủi ro, độ khẩn và sự cần thiết của tương tác trực tiếp.
8. Chuẩn bị bàn giao qua múi giờ, quản lý phụ thuộc và chuyển cấp mà không để việc đang chờ biến mất.
9. Dùng Scrum, Kanban, XP và các chỉ số flow để học hỏi, thay vì giám sát giờ online hoặc xếp hạng cá nhân.
10. Bảo vệ quyền riêng tư, bảo mật, khả năng tiếp cận và sự công bằng múi giờ.
11. Áp dụng ví dụ, mẫu, bài tập và checklist để cải thiện cách làm của một nhóm phân tán thực tế.

## 1. Minh bạch nghĩa là gì trong nhóm phân tán?

**Minh bạch (transparency)** là làm cho thông tin **đúng, đủ ngữ cảnh, kịp thời, dễ hiểu và có thể tra cứu lại** đối với những người cần nó để phối hợp hoặc ra quyết định.

| Thuộc tính | Câu hỏi kiểm tra | Ví dụ chưa đạt |
| --- | --- | --- |
| **Đúng** | Thông tin có phản ánh trạng thái được kiểm chứng? | Ticket ghi Done dù integration test phân quyền chưa đạt. |
| **Kịp thời** | Thông tin tới đúng người trước khi quyết định bị ảnh hưởng? | API đổi hợp đồng hôm trước nhưng consumer chỉ biết sau khi code lỗi. |
| **Có ngữ cảnh** | Người không dự họp có hiểu lý do, phạm vi, tác động? | “Đã chốt làm như cũ” mà không biết “cũ” là phiên bản nào. |
| **Dễ tìm** | Có nơi đáng tin để tra cứu bản hiện hành? | Quyết định nằm trong chat riêng của một người đang nghỉ. |
| **Có thể hành động** | Người đọc biết ai phải làm gì tiếp? | “Đang blocked” nhưng không nêu nguyên nhân hoặc người cần trả lời. |

Minh bạch **không phải công khai mọi thông tin cho mọi người**. Dữ liệu học viên, vấn đề nhân sự, secret, nội dung bảo mật và nghĩa vụ hợp đồng vẫn phải giới hạn quyền phù hợp. Mục tiêu là **người có thẩm quyền có đủ thông tin để ra quyết định an toàn**, không xóa mọi ranh giới riêng tư.

### Minh bạch khác báo cáo trạng thái

**Báo cáo hình thức:**

> “API 90% xong, không có vấn đề lớn.”

**Cập nhật có thể hành động:**

> “API lưu tiến độ đã merge và unit tests đạt. PBI vẫn In Progress vì integration test token hết quyền thất bại; chưa đạt DoD. Identity đang xác nhận hợp đồng từ chối truy cập. Nếu chưa có quyết định tại mốc đồng bộ kế tiếp, Sprint Goal có nguy cơ; Developers sẽ trao đổi PO về phạm vi.”

Cập nhật sau giải thích **điều đã kiểm chứng, điều chưa Done, rủi ro và bước tiếp**. Không cần đọc lại cả chuỗi chat để hiểu.

### Minh bạch khác giám sát

Số lần di chuột, ảnh chụp màn hình, thời gian bật camera, trạng thái online hoặc số tin nhắn không đo trực tiếp **giá trị người dùng, chất lượng hay khả năng tạo Increment**. Dùng chúng làm KPI có thể khiến mọi người giả lập hoạt động mà vẫn thiếu thông tin cần thiết.

Minh bạch Agile phục vụ **cải tiến hệ thống công việc**; không biến năng lực tự quản thành nghĩa vụ chứng minh hiện diện từng phút.

## 2. Ba lớp cần kết nối: mục tiêu, công việc, quyết định

Một nhóm phân tán có thể có rất nhiều công cụ: trang mục tiêu, board, repository, CI, chat, video call, trang thiết kế và dashboard. Vấn đề không phải có bao nhiêu công cụ, mà là **thông tin giữa chúng có tạo ra cùng một câu chuyện không**.

### Lớp A — Mục tiêu

- Sản phẩm phục vụ ai và giải quyết vấn đề nào?
- Product Goal hoặc mục tiêu tương đương đang là gì?
- Sprint Goal hoặc mục tiêu luồng ngắn hạn cần đạt?
- Điều gì được ưu tiên, điều gì chủ động chưa làm?
- Bằng chứng nào cho thấy người dùng có kết quả tốt hơn?

### Lớp B — Công việc

- Backlog có thứ tự và các PBI đủ được hiểu không?
- Mục nào Ready, In Progress, Review, Verify, Blocked, Done?
- Definition of Done và acceptance criteria nằm đâu?
- Phụ thuộc nào chưa giải quyết, ai có thể thực hiện hành động tiếp?
- Increment thực tế đã tích hợp, triển khai, phát hành hay nhận phản hồi?

### Lớp C — Quyết định

- Đề xuất nào còn đang thảo luận, quyết định nào đã có hiệu lực?
- Ai có thẩm quyền quyết, đã tham vấn ai?
- Vì sao chọn phương án này, đánh đổi và bất định là gì?
- Những PBI, API, người dùng hoặc nhóm nào bị ảnh hưởng?
- Khi nào cần xem lại hoặc thay quyết định?

| Thiếu lớp | Hệ quả thường gặp |
| --- | --- |
| **Mục tiêu** | Các địa điểm làm nhiều việc nhưng không cùng hướng tới kết quả. |
| **Công việc** | PBI bị chặn vô hình; “đang làm” có thể che việc chờ review nhiều ngày. |
| **Quyết định** | Tranh luận lặp lại, hợp đồng thay ngầm, người vắng mặt áp dụng cách cũ. |

~~~mermaid
flowchart TD
    A["Product Goal / giá trị người dùng"] --> B["Sprint Goal hoặc mục tiêu luồng"]
    B --> C["PBI nhỏ và thứ tự công việc"]
    C --> D["Develop, Review, Test, Integrate, DoD"]
    D --> E["Increment / Release phù hợp"]
    E --> F["Phản hồi người dùng và tín hiệu chất lượng"]
    F --> G["Điều chỉnh Backlog và quyết định"]
    G --> B
    G --> H["Decision log / ADR có hiệu lực"]
    H --> C
    C --> I["Blocked, phụ thuộc, rủi ro"]
    I --> H
~~~

Đây là **mô hình liên kết thông tin**, không phải yêu cầu mọi tổ chức dùng cùng một phần mềm hay chuyển qua từng ô theo thứ tự cố định.

## 3. Vì sao làm việc phân tán làm thông tin dễ đứt đoạn?

| Điều kiện | Rủi ro | Cơ chế bảo vệ |
| --- | --- | --- |
| Giờ làm không trùng | Người cần trả lời đang ngoài giờ, ticket chờ lâu. | Viết đủ bối cảnh, người nhận, mốc phản hồi và cách xử lý khẩn. |
| Trao đổi rải trong chat | Không rõ đâu là kết luận cuối. | Decision log có trạng thái và liên kết từ chat. |
| Không có trò chuyện hành lang chung | Một địa điểm nghe thay đổi, nơi khác không biết. | Sau trao đổi quan trọng, cập nhật nguồn có thẩm quyền. |
| Khác biệt ngôn ngữ và thuật ngữ | “Sắp Done”, “ưu tiên cao”, “đã duyệt” hiểu khác nhau. | Định nghĩa trạng thái, mức khẩn và ví dụ cụ thể. |
| Nhiều phụ thuộc liên nhóm | Mỗi nhóm nghĩ người khác đang giải quyết. | Owner của bước tiếp, tiêu chí hoàn tất phụ thuộc, escalation. |
| Quyết định theo giờ trụ sở | Người ở múi giờ khác bị loại khỏi đóng góp. | Xin ý kiến bất đồng bộ, luân phiên giờ họp khó. |
| Trạng thái bị sao chép | Board và báo cáo nói khác nhau. | Nguồn chính và đường dẫn, tránh nhập tay trùng lặp. |
| Áp lực chứng minh hoạt động | Cập nhật nhiều nhưng ít công việc Done. | Đo luồng, chất lượng và giá trị ở cấp hệ thống. |

Không nên dùng địa điểm hoặc quốc tịch để mặc định một nhóm “ngại phản biện” hay “chậm quyết định”. Cần làm rõ **cách giao tiếp của những người thực tế** và điều chỉnh theo tín hiệu quan sát.

## 4. Nguồn thông tin có thẩm quyền: không nhất thiết một công cụ duy nhất

**Single source of truth** hữu ích hơn khi hiểu là **mỗi loại thông tin có một nơi hiện hành được công nhận**. Các báo cáo và thông báo còn lại liên kết tới đó, không tạo nhiều bản sao có vẻ đều chính thức.

| Loại thông tin | Nguồn có thẩm quyền minh họa | Nơi khác nên làm gì? |
| --- | --- | --- |
| Product Goal và thứ tự Product Backlog | Nơi PO chịu trách nhiệm quản lý Product Backlog. | Link mục tiêu/PBI, không lập backlog ưu tiên riêng ở mỗi nơi. |
| Sprint Goal và kế hoạch Sprint | Sprint Backlog do Developers quản lý trong Scrum. | Nêu mục tiêu và liên kết trong cập nhật ngắn. |
| Trạng thái work item và blocked | Board với Definition of Workflow. | Chỉ tóm tắt thay đổi đáng chú ý, dẫn link item. |
| DoD và acceptance criteria | DoD chung, PBI có các ví dụ hành vi. | PR/CI trỏ đến tiêu chí và bằng chứng. |
| Code, kiểm thử và kết quả tích hợp | Repository, CI, môi trường kiểm thử phù hợp. | Gắn link, đừng báo test Green nếu thực tế Failed. |
| Quyết định kiến trúc/quy tắc liên nhóm | Decision log hoặc ADR có owner và trạng thái. | Thông báo quyết định kèm link, không chỉ chụp ảnh cuộc họp. |
| Hợp đồng API/sự kiện | Schema/contract do owner quản lý và kiểm thử. | PR, PBI và ADR liên kết tới phiên bản. |
| Incident và vận hành | Kênh/incident record chính thức theo chính sách. | Cập nhật tác động có quyền phù hợp, không phát tán dữ liệu nhạy cảm. |

### Quy tắc: thảo luận ở nhiều kênh, kết luận ở đúng nơi

Một quyết định có thể xuất hiện trong cuộc gọi kỹ thuật 15 phút, nhưng người tham gia phải **ghi trạng thái, lý do, phạm vi và người quyết định** tại nguồn chính; sau đó gửi liên kết vào những kênh cần biết.

**Mẫu thông báo:**

> “Đã chốt cách xử lý lỗi khi lưu tiến độ trong DEC-018 [link]. Áp dụng cho LEARN-41 từ bản contract v2; acceptance criteria và tests đã cập nhật. Các nhóm liên quan vui lòng xem phần ảnh hưởng trước khi triển khai.”

Chat là **kênh truyền đạt**; decision log là **dấu vết có thể kiểm chứng**.

### Tránh bản sao tự cập nhật

Nếu bảng đã lưu trạng thái, đừng yêu cầu nhập lại cùng các cột ở báo cáo ngày, báo cáo tuần và trang tổng hợp. Có thể dùng dashboard tự liên kết hoặc bản tóm tắt có ngày cập nhật, nhưng dữ liệu **phải truy về nguồn**.

## 5. Minh bạch mục tiêu giúp nhóm tự quyết mà không phải chờ PO online

Khi người ở địa điểm khác bắt đầu làm việc lúc PO đã rời máy, một mục tiêu đủ rõ giúp họ **chọn bước đúng** mà không cần xin phép cho mọi chi tiết.

Một mục tiêu tốt nên mô tả:

- **Ai** được phục vụ?
- **Vấn đề** người đó đang gặp là gì?
- **Kết quả** có ý nghĩa nào cần đạt?
- **Giới hạn phạm vi** và điều kiện chất lượng nào phải giữ?
- **Tín hiệu** nào cho thấy đã tạo giá trị hoặc cần đổi hướng?

**Mục tiêu yếu:** “Hoàn thành module Progress và 30 story points.”

**Mục tiêu có giá trị:**

> “Giúp học viên đã bắt đầu học Java quay lại đúng video đang học mà không phải tìm thủ công, giữ tiến độ và quyền truy cập chính xác; kiểm tra trải nghiệm với một nhóm học viên được phép.”

| Cấp mục tiêu | Ví dụ | Dùng để quyết định điều gì? |
| --- | --- | --- |
| **Product Goal** | Học viên duy trì việc học dễ dàng nhờ quay lại đúng phần đang dở. | Hướng ưu tiên sản phẩm dài hạn. |
| **Sprint Goal** | Học viên có quyền mở lại một video từ vị trí đã lưu qua phiên đăng nhập. | Những lựa chọn/nghiệp vụ nào quan trọng trong Sprint này. |
| **PBI/Tasks** | Lưu vị trí, đọc vị trí, kiểm tra quyền, xử lý lỗi, nối UI và test. | Những hoạt động cần để đạt mục tiêu. |

Trong **Scrum**, Product Goal là commitment gắn với Product Backlog; Sprint Goal gắn với Sprint Backlog; Definition of Done gắn với Increment. Mục tiêu không phải danh sách chi tiết mọi bước triển khai.

### Mục tiêu phải được xem lại khi có phản hồi

Nếu thử nghiệm cho thấy người học không tìm thấy nút Học tiếp, PO có thể ưu tiên cách hiển thị trước khi đầu tư đồng bộ offline. Khi ưu tiên đổi, cần **cập nhật Product Backlog ở nơi chính và thông báo tác động**, không chỉ nói với vài người trong một cuộc gọi.

### Một Sprint Goal không chỉ là bảng điểm

Velocity và story points là kỹ thuật ước lượng tùy chọn, không phải mục tiêu bắt buộc của Scrum. Câu “đạt 30 points” không chứng minh người học có thể tiếp tục video, và có thể khuyến khích hạ DoD để đạt số.

## 6. Minh bạch công việc: bảng phải nhìn thấy luồng và nơi chờ

Một board tốt không chỉ gắn người với ticket. Nó cho thấy **điều gì đang được hoàn tất, điều gì bị chặn, phụ thuộc ở đâu và người nào có thể làm bước tiếp theo**.

~~~text
Product Goal: Học viên quay lại bài đang học dễ dàng
Sprint Goal: Khôi phục vị trí video qua phiên đăng nhập an toàn

Ready -> Develop (WIP <= 3) -> Review (WIP <= 2) -> Verify -> Done

LEARN-41   Develop   Lưu/đọc tiến độ         Next: test lỗi mạng
LEARN-42   Review    Nút "Học tiếp"         Next: accessibility review
LEARN-43   Blocked   Tích hợp Identity     Next: ID-12 xác nhận quyền
LEARN-44   Done      Chưa có tiến độ       Evidence: test + CI + DoD
~~~

Các cột và giới hạn WIP chỉ là **ví dụ**, nhóm phải chọn theo năng lực và loại việc. Trong Kanban, cần **Definition of Workflow** rõ: loại work item, Started/Finished, trạng thái, chính sách WIP và cách quản lý blocked.

### Một PBI nên thể hiện những gì?

| Trường | Ví dụ | Vì sao hữu ích từ xa? |
| --- | --- | --- |
| **Outcome** | Học viên mở lại video từ vị trí đã lưu. | Người khác hiểu mục đích, không chỉ mã ticket. |
| **Acceptance criteria** | Có dữ liệu, chưa có dữ liệu, lỗi mạng, trái quyền. | Giảm hiểu khác khi PO không online. |
| **Trạng thái đúng** | Verify; kiểm thử tích hợp chưa đạt. | Tránh nhầm code xong với Done. |
| **Next action/owner** | Identity xác nhận contract v2. | Biết cần hỏi ai và câu hỏi nào. |
| **Phụ thuộc** | ID-12, policy token hết quyền. | Người nhận thấy rủi ro. |
| **Blocked reason + checkpoint** | Chờ ví dụ response; xem lại ở lần phối hợp kế tiếp. | Không để ticket chờ vô hạn. |
| **Bằng chứng** | PR, CI, contract test, demo. | Người khác có thể kiểm tra độc lập. |
| **Điều kiện hoàn tất** | DoD và hành vi tích hợp đúng. | Bảo vệ chất lượng qua các địa điểm. |

Không nhất thiết ép mọi task rất nhỏ điền nhiều trường. **Mức thông tin phụ thuộc tác động, phụ thuộc và rủi ro**.

## 7. Trạng thái “đang làm” khác “đã Done”

Các nhãn cần có định nghĩa chung:

- **Ready:** đã đủ hiểu và có điều kiện để kéo vào làm theo chính sách.
- **In Progress:** công việc thực sự bắt đầu, chưa đạt Done.
- **Blocked:** không thể tiếp tục bước cần thiết vì chờ phụ thuộc/quyết định/môi trường; phải ghi lý do và next action.
- **Review:** chờ hoặc đang review theo tiêu chí được thống nhất.
- **Verify/Integrate:** xác minh hành vi tích hợp, rủi ro và DoD.
- **Done:** PBI/Increment đạt điều kiện hoàn tất tương ứng và có thể dùng trong phạm vi sản phẩm.

**“Đã code xong 90%” không phải Done.** Nếu UI chưa tích hợp với API hoặc kiểm thử quyền thất bại, người dùng vẫn chưa có hành vi đầu cuối đáp ứng DoD. Có thể ghi tiến bộ kỹ thuật, nhưng không đổi nghĩa trạng thái.

### Blocked không phải để đổ lỗi

**Yếu:** “Blocked by backend.”

**Hữu ích:**

> “LEARN-43 chờ Identity xác nhận hành vi với token đã hết quyền. Learning đã gửi hợp đồng và test thất bại trong ID-12. Identity là owner của câu trả lời; nếu qua checkpoint tiếp theo chưa rõ, Developers sẽ trao đổi tác động Sprint Goal và ưu tiên lát khác.”

Blocked là **tín hiệu của hệ thống cần giải quyết**, không phải thẻ gắn lỗi cá nhân hoặc nhóm.

### WIP và sự ưu tiên hoàn tất

Nếu 12 ticket đang In Progress nhưng không có PBI Done, thêm một ticket mới có thể khiến luồng chậm hơn. Một chính sách WIP giúp nhóm **tập trung gỡ blocker và hoàn tất**, thay vì tối đa hóa số việc đang mở.

## 8. Definition of Done là tiêu chuẩn chung qua địa điểm

**Definition of Done (DoD)** giúp Developers, QA, PO và vận hành hiểu cùng một nghĩa của Increment hoàn tất. Ví dụ với tính năng lưu tiến độ:

- Logic nghiệp vụ đã tích hợp với phần sản phẩm hiện có.
- Acceptance criteria và trường hợp biên/lỗi quan trọng được kiểm chứng.
- Không lộ dữ liệu tiến độ học viên khác; kiểm tra quyền đầy đủ theo chính sách.
- Không báo lưu thành công khi dữ liệu chưa ghi được.
- Unit/integration tests phù hợp đạt và không phá hồi quy.
- Có khả năng nhận diện/xử lý lỗi vận hành khi phạm vi yêu cầu.
- Hướng dẫn hoặc thông tin hỗ trợ được cập nhật đúng phạm vi tính năng.

**Acceptance criteria** mô tả hành vi của một PBI; **DoD** là tiêu chuẩn chất lượng chung của Increment. Không được chuyển PBI sang Done khi các điều kiện áp dụng chưa đạt chỉ vì đội ở múi giờ khác cần báo cáo đẹp.

### Scrum và nhiều Scrum Teams cùng một sản phẩm

Theo Scrum Guide 2020, nhiều Scrum Teams cùng làm một sản phẩm cần **cùng Product Goal, Product Backlog, Product Owner**, và **Definition of Done chung**. Increment của họ phải hoạt động cùng nhau; không thể mỗi đội tự dùng một định nghĩa Done mâu thuẫn để ghi công việc hoàn tất.

### Done không đồng nghĩa release

Increment đạt DoD có thể được bàn giao trước Sprint Review khi phù hợp. Nhưng release có thể phụ thuộc điều kiện bảo mật, vận hành và thẩm quyền. Bảng nên phân biệt **Done, Deployed, Released, Feedback Observed**, thay vì báo mọi người dùng đã có tính năng ngay khi PR được merge.

## 9. Minh bạch quyết định: một đề xuất chưa phải điều đã chốt

Nhiều lỗi liên nhóm xuất phát từ việc một nhóm coi cuộc thảo luận là quyết định cuối, trong khi nhóm khác chưa được thông báo hoặc chưa có quyền phê duyệt.

Một quyết định quan trọng nên có:

1. **Vấn đề/bối cảnh:** cần giải quyết gì, bằng chứng nào?
2. **Lựa chọn hợp lý:** gồm cả giữ hiện trạng khi cần.
3. **Người có thẩm quyền:** theo quyền sản phẩm, sở hữu hợp đồng hoặc chính sách tổ chức.
4. **Người cần tham vấn:** nhóm bị ảnh hưởng và chuyên gia rủi ro.
5. **Kết luận, lý do và đánh đổi:** đã chọn gì, hy sinh gì?
6. **Phạm vi, ngày hiệu lực và phiên bản:** áp dụng ở đâu, từ khi nào?
7. **Hệ quả công việc:** PBI/PR/contract/test/release nào cần đổi?
8. **Điều kiện xem lại:** tín hiệu nào khiến quyết định cần thay thế?

### Trạng thái quyết định

| Trạng thái | Ý nghĩa |
| --- | --- |
| **Proposed** | Có đề xuất, chưa có hiệu lực. |
| **Under review** | Đang lấy ý kiến hoặc chờ người có thẩm quyền. |
| **Accepted/Decided** | Đã chốt trong phạm vi và thời điểm xác định. |
| **Rejected** | Đã cân nhắc và không chọn, có lý do. |
| **Superseded** | Đã được quyết định mới thay thế; giữ lịch sử. |
| **Expired/Needs review** | Quyết định tạm/ngoại lệ phải xem lại. |

Tên trạng thái có thể thay đổi theo tổ chức, nhưng **không được nhập nhằng** giữa đề xuất và chính sách đã có hiệu lực.

## 10. Decision log, RFC và ADR: không phải mọi việc đều cần tài liệu dài

| Loại | Cách ghi thường đủ | Ví dụ |
| --- | --- | --- |
| Cục bộ, dễ đảo ngược | PR/issue + lý do và test. | Đổi tên phương thức nội bộ. |
| Thứ tự công việc ngắn hạn | Product/Sprint Backlog với lý do phù hợp. | Ưu tiên sửa lỗi quyền cao hơn cải tiến giao diện. |
| Chính sách nhóm | Working agreement/decision log. | WIP limit và kênh xử lý blocked. |
| Hợp đồng liên nhóm | RFC/ADR ngắn + schema/contract test. | API ProgressSaved đổi mã lỗi. |
| Rủi ro cao, khó đảo ngược | ADR, phương án chuyển đổi, người có thẩm quyền. | Chuyển quyền sở hữu dữ liệu người học. |
| Sự cố khẩn | Incident record và quyết định xử lý phù hợp. | Tạm dừng release có nguy cơ lộ dữ liệu. |

**RFC** thường phục vụ xin ý kiến trước khi quyết định. **ADR** ghi lại quyết định kiến trúc, lý do, đánh đổi và bối cảnh. Có thể dùng một tài liệu đi từ Proposed tới Accepted nếu trạng thái rõ.

### Mẫu quyết định có thể dùng

~~~text
DECISION-ID: DEC-018
Tiêu đề: Không xác nhận "Đã lưu" trước khi API xác nhận thành công
Trạng thái: ACCEPTED
Hiệu lực: YYYY-MM-DD, timezone được công bố

Vấn đề:
  UI báo "Đã lưu" ngay sau khi người học nhấn Pause,
  kể cả khi request bị lỗi mạng.

Phương án:
  A. Hiện thành công ngay, thử lại ở nền.
  B. Chờ xác nhận hoặc hiển thị trạng thái đang lưu/thử lại.

Quyết định:
  Chọn B cho lát đầu theo ngữ nghĩa dữ liệu đã thống nhất.

Lý do / đánh đổi:
  Không báo thành công giả, nhưng UX có thể phải chờ.

Thẩm quyền và tham vấn:
  Người có quyền quyết định được xác định theo phạm vi sản phẩm/kỹ thuật.
  Tham vấn PO, Learning, UX/QA.

Tác động:
  LEARN-41, acceptance criteria AC-3, negative integration tests.

Điều kiện xem lại:
  Có dữ liệu thực về độ trễ UX hoặc thay đổi chiến lược offline.

Liên kết:
  Ticket, hợp đồng API, PR, test, mockup.
~~~

Nếu DEC-018 về sau thay đổi, nên tạo bản mới **supersedes DEC-018**, thay vì sửa lịch sử để người đọc không còn hiểu vì sao code cũ từng hợp lý.

## 11. Ai có quyền quyết định? Đừng tạo hai nguồn thẩm quyền

Trong Scrum:

- **Product Owner** chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả, bao gồm thứ tự công việc.
- **Developers** tạo Increment đáp ứng DoD, tự quản kế hoạch kỹ thuật và Sprint Backlog.
- **Scrum Master** chịu trách nhiệm về hiệu quả Scrum, hỗ trợ nhóm và tổ chức tháo gỡ trở ngại.

Không nên để một quản lý ở địa điểm khác tự sắp Product Backlog thay Product Owner rồi bắt nhóm gọi đó là “ưu tiên Agile”. Ngược lại, Product Owner cũng không tự có quyền bỏ tiêu chuẩn bảo mật bắt buộc hoặc ép Developers gọi phần chưa đạt DoD là Done.

| Quyết định | Đầu mối phù hợp | Người cần tham vấn |
| --- | --- | --- |
| Thứ tự Product Backlog | Product Owner trong Scrum. | Developers và stakeholders. |
| Cách triển khai Sprint Goal | Developers. | PO, nhóm sở hữu phụ thuộc, reviewer. |
| Cải tiến việc sử dụng Scrum | Scrum Team, Scrum Master hỗ trợ. | Người có thể tháo trở ngại. |
| Thay API của Identity được Learning dùng | Nhóm sở hữu hợp đồng theo cơ chế liên nhóm. | Consumers, QA/security/ops theo rủi ro. |
| Chấp nhận nghĩa vụ/rủi ro tuân thủ | Người/bộ phận được tổ chức trao thẩm quyền. | Các nhóm bị ảnh hưởng. |
| Bật release cho người dùng thật | Người có thẩm quyền phát hành theo chính sách. | PO, Developers, vận hành/bảo mật. |
| Điều phối incident nghiêm trọng | Incident owner/commander theo quy trình. | Nhóm dịch vụ và người liên quan. |

**Tham vấn không luôn đòi hỏi đồng thuận tuyệt đối.** Có thể dùng cơ chế lấy ý kiến và người có quyền chốt. Với quyết định cần phê duyệt chính thức, **sự im lặng của người được hỏi không tự bằng phê duyệt**.

## 12. Một quy trình ra quyết định bất đồng bộ có điểm kết thúc

Một RFC đăng lên rồi không ai trả lời có thể khiến nhóm chờ vô hạn. Một quy trình ngắn cần có **owner và mốc quyết định**:

1. **Đăng vấn đề và đề xuất:** mục tiêu, lựa chọn, đánh đổi, bằng chứng, phạm vi.
2. **Xác định đúng đối tượng tham vấn:** người chịu ảnh hưởng và chuyên gia cần thiết.
3. **Nêu kỳ vọng phản hồi:** kênh, thời hạn tương ứng múi giờ và mức rủi ro.
4. **Làm rõ bất đồng:** hỏi về điều kiện, thử nhỏ nếu còn bất định kỹ thuật.
5. **Người có thẩm quyền chốt:** không xem số người emoji đồng ý là cơ sở duy nhất.
6. **Đưa quyết định về nguồn chính:** Accepted, lý do, hiệu lực, owner, liên kết.
7. **Cập nhật những việc bị ảnh hưởng:** backlog, API, tests, rollout.
8. **Xem lại nếu điều kiện thay đổi:** giữ dấu vết để người đến sau hiểu.

~~~mermaid
flowchart TD
    P["Proposal / RFC"] --> C["Nhận ý kiến người bị ảnh hưởng"]
    C --> D{"Đủ thông tin và đúng thẩm quyền?"}
    D -->|"Chưa"| Q["Làm rõ, thử nhỏ hoặc chuyển cấp"]
    Q --> C
    D -->|"Có"| E["Accepted: lý do, owner, hiệu lực"]
    E --> L["Liên kết backlog, PR, contract và thông báo"]
    L --> V["Quan sát hệ quả và rủi ro"]
    V --> R{"Cần thay quyết định?"}
    R -->|"Không"| K["Theo dõi"]
    R -->|"Có"| N["Tạo quyết định thay thế, giữ lịch sử"]
    N --> P
~~~

Cần phân biệt **thời hạn xin ý kiến** với **phê duyệt bắt buộc**. Những vấn đề bảo mật, pháp lý, dữ liệu riêng tư hoặc hợp đồng không được tự hợp thức hóa chỉ vì hết thời hạn mà chưa có câu trả lời.

## 13. Giao tiếp bất đồng bộ và đồng bộ: chọn đúng phương tiện

Không phải mọi vấn đề cần họp video, nhưng cũng không nên cố giải quyết sự cố nghiêm trọng qua một chuỗi comment kéo dài.

| Tình huống | Kênh thường phù hợp | Mục đích |
| --- | --- | --- |
| Cập nhật trạng thái thường nhật | Board/PBI + ghi chú ngắn. | Người khác nắm tình trạng khi bắt đầu giờ làm. |
| Đề xuất thiết kế chưa khẩn | RFC/ADR bất đồng bộ. | Có thời gian đọc, phản biện và giữ dấu vết. |
| Làm rõ acceptance criteria | Comment tại PBI; gọi ngắn nếu khó hiểu. | Giữ thông tin gần công việc. |
| Xung đột hợp đồng giữa nhiều nhóm | Trao đổi có cấu trúc, có thể gọi ngắn rồi ghi ADR. | Thoát vòng tranh luận không kết thúc. |
| Incident nghiêm trọng | Kênh khẩn/bridge theo chính sách trực. | Phản ứng kịp thời và có điều phối. |
| Kiểm tra kết quả sản phẩm | Review với stakeholder, dữ liệu và mục tiêu. | Học và thay đổi ưu tiên. |
| Thông báo quyết định đã chốt | Decision log + message có link. | Người vắng mặt biết chính xác điều có hiệu lực. |

**Quy tắc thực hành:** dùng async khi việc có thể chờ và cần nghiên cứu; dùng tương tác trực tiếp khi hiểu sai kéo dài hoặc cần giải quyết kịp thời; **sau cuộc gọi vẫn phải ghi quyết định**.

### Không bắt mọi người phản hồi ngay

Một tin nhắn thường không nên mặc định yêu cầu hồi đáp tức thời, nhất là ngoài giờ làm. Nhóm cần quy định **kỳ vọng phản hồi cho việc thường, việc có hạn và sự cố khẩn**; nếu người nhận đang ngoài giờ, có đường chuyển cấp phù hợp thay vì giục họ liên tục.

## 14. Múi giờ: minh bạch để công bằng, không ép cùng lịch

Nếu một nhóm ở Việt Nam, người khác ở châu Âu và Bắc Mỹ, lịch “tiện cho trụ sở” có thể là đêm của một nhóm khác. Điều đó làm cho người dự họp thuận tiện có ảnh hưởng nhiều hơn và những người vắng mặt phải làm theo quyết định không được tham vấn.

### Các chính sách nên cân nhắc

1. Công bố múi giờ làm việc và thời gian liên hệ bình thường **chỉ ở mức cần cho phối hợp**.
2. Dùng timezone IANA rõ như **Asia/Ho_Chi_Minh, Europe/Berlin, America/Toronto**, hoặc timestamps UTC.
3. Đừng giả định chênh lệch giờ giữa các nơi luôn cố định vì một số khu vực có **giờ mùa hè**.
4. Nếu cuộc họp khó tránh, **luân phiên giờ bất tiện** khi phù hợp, không để một địa điểm gánh mãi.
5. Gửi mục tiêu cuộc họp và tài liệu trước để người không dự có thể bình luận.
6. Ghi kết luận, owner, hạn và liên kết sau cuộc họp.
7. Không coi trả lời ngoài giờ làm là chuẩn hiệu suất, trừ ca trực/điều kiện đã thỏa thuận.
8. Có kênh xử lý khẩn thực sự, không biến mọi tin nhắn thành “urgent”.

### Ghi thời điểm sao cho không mơ hồ

“9 giờ tối chỗ bạn” không còn rõ khi người nhận đổi địa điểm hoặc sau chuyển giờ mùa hè. Nên ghi **ngày, giờ, timezone rõ** hoặc dùng lịch mời xử lý múi giờ, để người đọc tự chuyển giờ địa phương.

### Công bằng không nghĩa mọi người dự mọi cuộc gọi

Có thể chia thành cuộc trao đổi nhỏ của những người cần giải quyết vấn đề và vòng bình luận bất đồng bộ với người chịu ảnh hưởng. Quan trọng là **người có trách nhiệm không bị loại khỏi quyết định**, và những người không dự vẫn có nguồn thông tin chính xác.

## 15. Daily update: viết để người khác hành động, không viết để chứng minh bận

Một bản cập nhật ngắn theo công việc có thể tiết kiệm nhiều giờ hỏi lại.

~~~text
WORK UPDATE — YYYY-MM-DD, Asia/Ho_Chi_Minh

Mục tiêu liên quan:
  Sprint Goal "Học tiếp qua phiên đăng nhập".

Đã được kiểm chứng:
  LEARN-41: API đọc/lưu đã merge; unit tests đạt.
  Chưa Done: integration test token hết quyền thất bại.

Đang tập trung:
  Nối UI với API thật và sửa xử lý lỗi.

Blocked / cần quyết định:
  ID-12: Identity xác nhận ngữ nghĩa DENIED.
  Owner: nhóm Identity; checkpoint: lần phối hợp kế tiếp.

Rủi ro:
  Nếu chưa đạt negative test, Sprint Goal chưa đáp ứng DoD.

Bằng chứng:
  Link issue, PR, CI và contract.

Hành động cho người khác:
  Identity phản hồi contract; reviewer xem nhánh lỗi.
  Không cần phản hồi tức thì ngoài chính sách sự cố.
~~~

Nếu ticket đã được cập nhật đầy đủ và không có thay đổi quan trọng, không cần thêm một bản cập nhật dài giống hệt. **Giảm lặp lại, tăng khả năng hành động** là tiêu chí.

### Daily Scrum và thông báo bất đồng bộ

Trong **Scrum đầy đủ**, Daily Scrum là sự kiện **15 phút của Developers** để kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog. Không bắt buộc mỗi người lần lượt trả lời ba câu “hôm qua/hôm nay/trở ngại”. Nhóm có thể chuẩn bị async status để Daily Scrum tập trung giải quyết vấn đề.

Tuy nhiên, gửi status bất đồng bộ **không tự động thay thế sự kiện cốt lõi Daily Scrum** nếu vẫn tuyên bố áp dụng đầy đủ Scrum. Nhóm có thể chọn mô hình khác phù hợp múi giờ, nhưng cần mô tả trung thực phương pháp đang dùng.

## 16. Bàn giao qua múi giờ: đủ ngữ cảnh để người sau không phải điều tra lại

Làm việc qua nhiều múi giờ có thể tạo cơ hội tiếp tục công việc khi một nhóm kết thúc ngày. Nhưng **follow-the-sun không tự động tăng tốc độ**: nhiều lần bàn giao thiếu ngữ cảnh sẽ làm thời gian chờ, số vòng hỏi lại và lỗi tích hợp tăng lên.

Một bàn giao tốt cần ít nhất sáu phần:

| Phần | Nội dung | Câu hỏi của người nhận |
| --- | --- | --- |
| **Mục tiêu** | Hành vi hoặc kết quả nào cần đạt? | Vì sao công việc này quan trọng? |
| **Trạng thái đã xác minh** | Điều đã chạy/test đạt và điều chưa đạt. | Có thể tin vào phần nào? |
| **Bằng chứng** | Link PR, CI, test, contract, môi trường hoặc log đã bảo vệ dữ liệu. | Có thể tiếp tục mà không làm lại điều tra? |
| **Bước tiếp theo** | Một hành động cụ thể và kết quả mong đợi. | Mình cần làm gì trước? |
| **Rủi ro và giới hạn** | Điều chưa rõ, việc tuyệt đối không được bỏ qua. | Nếu làm sai sẽ ảnh hưởng điều gì? |
| **Owner và đường phản hồi** | Ai nhận hành động, cách trả lời và chuyển cấp. | Nếu bị chặn thì hỏi ai? |

### Một bàn giao hữu ích

~~~text
HANDOFF — LEARN-41: lưu tiến độ video

Mục tiêu:
  Học viên có quyền mở lại đúng vị trí qua các phiên đăng nhập.
  Không tiết lộ tiến độ riêng tư của người khác.

Đã xác minh:
  API đọc/lưu đạt unit tests.
  Contract v2 quy định token hết quyền phải bị từ chối.

Chưa Done:
  Integration test với Identity thất bại ở nhánh cache.
  Vì vậy PBI vẫn In Progress, chưa đạt DoD.

Việc tiếp theo:
  Identity kiểm tra policy cache/invalidation trong ID-12.
  Learning sau đó chạy lại negative tests và integration suite.

Bằng chứng:
  Link failing test, PR, contract v2, log đã loại thông tin nhạy cảm.

Không được làm:
  Không bỏ bước kiểm tra quyền chỉ để làm test Green.

Owner:
  Identity cho hành động xác nhận hợp đồng;
  Learning cho việc hoàn tất PBI và tích hợp.
  Sự cố bảo mật cấp cao dùng incident process ngay.
~~~

Người nhận có thể tiếp tục bằng thông tin đầy đủ, không cần hỏi lại toàn bộ “hôm qua đã làm gì?”.

### Handoff không được làm mất trách nhiệm đầu cuối

Một nhóm có thể đang hỗ trợ phụ thuộc, nhưng người chịu trách nhiệm đưa PBI trở về Done phải rõ ràng. “Đã chuyển sang nhóm khác” **không có nghĩa không còn ai theo dõi**.

### Khi không nên bàn giao

Nếu công việc cần hiểu biết sâu, một lần chuyển người giữa hai múi giờ có thể tốn thời gian hơn để cùng người ban đầu tiếp tục ngày sau. Hãy cân nhắc **mức độ độc lập, tài liệu, khả năng xác minh và chi phí hiểu lại**; không cố tạo handoff vì muốn dùng tối đa 24 giờ trong ngày.

## 17. Phụ thuộc liên nhóm: minh bạch blocked và đường xử lý

Một work item có thể bị chặn vì:

- Chưa thống nhất acceptance criteria.
- Hợp đồng API từ nhóm khác thay đổi.
- Không có môi trường tích hợp.
- Cần người có thẩm quyền quyết định về bảo mật.
- Review chuyên môn đang có hàng chờ.
- Một phần dữ liệu hoặc nội dung học chưa được cung cấp.

**Blocked không phải lỗi của một cá nhân.** Nó là tín hiệu nhóm cần điều chỉnh cách phối hợp.

### Dependency card mẫu

~~~text
DEPENDENCY: DEP-014
Nguồn: LEARN-41 cần hợp đồng Identity ID-12.

Câu hỏi đang chặn:
  Token đã bị thu hồi có phải luôn nhận từ chối truy cập
  khi yêu cầu đọc tiến độ?

Bằng chứng:
  Link contract v2, failing integration test, kịch bản nghiệp vụ.

Owner cung cấp:
  Nhóm sở hữu API Identity.

Owner tích hợp:
  Learning Developers.

Tiêu chí xử lý xong phụ thuộc:
  Contract được xác nhận và negative test đạt trên phiên bản phù hợp.

Tác động:
  Không thể xác nhận DoD của LEARN-41; Sprint Goal có rủi ro.

Checkpoint:
  Kỳ phối hợp kỹ thuật tiếp theo theo lịch đã thống nhất.

Escalation:
  Đầu mối có thẩm quyền nếu quá mốc hoặc rủi ro tăng.
  Vấn đề bảo mật nghiêm trọng dùng quy trình incident.
~~~

### Chính sách chuyển cấp có thể dùng

1. **Ghi blocked sớm** cùng nguyên nhân có thể xác minh.
2. **Hỏi đúng owner**, nêu một câu hỏi cụ thể và tác động nếu chậm.
3. **Theo dõi thời điểm phản hồi** theo mức khẩn và múi giờ.
4. Nếu hết thời điểm mà không có giải pháp, **chuyển cấp đúng người có quyền**.
5. Nếu Product/Sprint Goal bị ảnh hưởng, **thông báo PO và trao đổi phương án phạm vi**.
6. Khi phụ thuộc được gỡ, **cập nhật trạng thái và liên kết bằng chứng**.

Một SLA phản hồi cho câu hỏi thường không phải bảo đảm mọi người sẽ trả lời ngoài giờ làm. Ngoại lệ khẩn cần cơ chế **trực, người thay thế và thẩm quyền** tương ứng.

## 18. Làm rõ đâu là quyết định, đâu là yêu cầu và đâu là thông tin

Trong chat phân tán, các câu “nên”, “cần”, “đã quyết”, “có thể” dễ bị hiểu lẫn nhau. Có thể dùng nhãn rõ:

| Nhãn | Cách dùng | Ví dụ |
| --- | --- | --- |
| **FYI** | Cung cấp thông tin, không yêu cầu hành động. | CI đã triển khai bản thử lên staging. |
| **QUESTION** | Cần câu trả lời để hiểu một vấn đề. | Token đã thu hồi có thể được cache bao lâu? |
| **REQUEST** | Cần ai đó thực hiện hành động. | Identity cập nhật contract v2 và test ví dụ. |
| **PROPOSAL** | Đề xuất chưa có hiệu lực. | Đề xuất chuyển phản hồi lỗi sang HTTP 409. |
| **DECISION** | Đã được người có quyền chốt; có phạm vi/hiệu lực. | DEC-018 được Accepted, áp dụng từ version v2. |
| **RISK/BLOCKER** | Có khả năng ảnh hưởng mục tiêu hoặc DoD. | Không thể kiểm thử quyền do API chờ xác nhận. |
| **INCIDENT** | Sự cố cần cơ chế xử lý theo mức nghiêm trọng. | Dữ liệu tiến độ cá nhân bị lộ qua endpoint. |

Đây không phải định dạng bắt buộc phải đặt trước **mọi** tin nhắn. Khi tác động liên nhóm hoặc có rủi ro, nhãn rõ có thể giúp người đọc không nhầm **một gợi ý trong chat** thành **một quyết định đang được áp dụng**.

### Một ví dụ ghi nhận quyết định sau cuộc họp

**Không rõ:**

> “Mọi người làm theo cách mới nhé.”

**Rõ hơn:**

> “DECISION — DEC-018 đã Accepted: giao diện chỉ hiện ‘Đã lưu’ sau xác nhận thành công từ API; nếu lỗi, hiển thị trạng thái thử lại. Áp dụng từ contract v2 cho LEARN-41. Lý do, phạm vi, người quyết định và test: [link].”

Nếu có người quan trọng chưa được tham vấn, cần xử lý theo cơ chế quyền trước khi chuyển từ Proposed thành Accepted.

## 19. Done, Deployed, Released và Feedback Observed

Một nguyên nhân báo cáo sai rất phổ biến: nhóm đã merge code, Product Owner hiểu là người dùng đã có tính năng, còn vận hành biết feature flag vẫn tắt.

Nên phân biệt:

| Mốc | Ý nghĩa | Bằng chứng |
| --- | --- | --- |
| **Done** | Increment đáp ứng DoD, có thể sử dụng trong phạm vi đã xác định. | Test, tích hợp, review, yêu cầu chất lượng. |
| **Deployed** | Phiên bản đã đưa lên môi trường tương ứng. | Build/version, deployment records. |
| **Released** | Khả năng đã được mở cho nhóm người dùng xác định. | Flag, rollout record, thông báo phù hợp. |
| **Feedback Observed** | Có dữ liệu/phản hồi thực giúp xem lại giả thuyết. | Telemetry hợp lệ, phỏng vấn, lỗi và phản hồi người dùng. |

### Bản ghi phát hành minh họa

~~~text
Feature: Học tiếp / Increment I1
Done: YES — DoD + negative integration tests đã đạt
Deployed: YES — production version v1.8, feature flag OFF
Released: NO — người học chưa được mở khả năng
Release decision owner: theo chính sách phát hành tổ chức

Rủi ro còn lại:
  Cần kiểm tra telemetry và khả năng hỗ trợ nhóm dùng thử.

Kế hoạch:
  Mở cho cohort có quyền khi đủ điều kiện.
  Theo dõi lỗi, thời gian khôi phục tiến độ, task success.
  Thu phản hồi định tính và cập nhật Product Backlog.
~~~

Trong Scrum, **Sprint Review không phải một cổng release bắt buộc**. Increment có thể bàn giao trước khi Sprint kết thúc khi điều kiện phù hợp; tuy nhiên, việc release còn chịu các điều kiện an toàn, hợp đồng và thẩm quyền tổ chức.

### Feature flag không tự bảo vệ dữ liệu

Tắt flag có thể ngăn truy cập giao diện nhưng **không hoàn tác dữ liệu đã ghi sai, sự kiện đã gửi hoặc hành động ngoài hệ thống**. Với thay đổi lưu tiến độ, cần kiểm soát dữ liệu và phương án khôi phục thực tế.

### Phản hồi phải đi về mục tiêu và backlog

Nếu người học nói họ không tìm được nút “Học tiếp”, đừng để phản hồi chỉ nằm trong chat hỗ trợ. Nên ghi bằng chứng, xem tác động Product Goal, để PO trao đổi thứ tự PBI với Developers, chọn lát cải thiện, giao và tiếp tục quan sát.

## 20. Kỹ thuật XP và kiểm thử làm trạng thái đáng tin hơn

Thông tin chỉ minh bạch nếu **bằng chứng có thể tin được**. Các thực hành Extreme Programming hỗ trợ điều đó:

- **Test-driven development (TDD):** làm rõ hành vi bằng kiểm thử và nhận phản hồi khi code đổi.
- **Continuous Integration (CI):** tích hợp thường xuyên, phát hiện hồi quy và xung đột sớm.
- **Refactoring:** giữ cấu trúc dễ thay mà không đổi hành vi ngoài dự định.
- **Pair programming/review:** chia sẻ ngữ cảnh và phát hiện giả định khác nhau.
- **Simple design:** ưu tiên giải pháp đủ để tạo Increment, tránh tạo phụ thuộc không cần thiết.
- **Small releases:** đưa giá trị tới người dùng sớm khi đủ điều kiện.

### Liên kết PR, CI và PBI

Một PBI có thể được kết nối như sau:

~~~text
PBI LEARN-41
  Goal: Người học mở lại video qua phiên đăng nhập
  Acceptance criteria: AC-1, AC-2, AC-3
  PR: #248 — xử lý lưu/đọc vị trí
  CI: run 2034 — unit tests PASS
  Integration: run 2035 — quyền truy cập FAIL
  Status: Verify, NOT Done
  Decision: DEC-018 về thông báo "Đã lưu"
  Next: sửa negative case, chạy lại integration suite
~~~

Nếu báo cáo chỉ dựa vào “PR merged”, nhóm ở địa điểm khác có thể coi PBI Done trong khi kết quả kiểm thử chưa phù hợp. Nối **đầu ra kỹ thuật với DoD** giúp giảm diễn giải sai.

### Kiểm thử hợp đồng liên nhóm

Khi API Identity đổi ý nghĩa mã lỗi, không chỉ chat “đã đổi”. Nhóm nên có **versioned contract** và kiểm thử producer/consumer phù hợp, cùng kịch bản nghiệp vụ để tránh trường hợp schema đúng nhưng ý nghĩa sai.

## 21. Tính an toàn, quyền riêng tư và an toàn tâm lý

Minh bạch không cho phép đăng bất cứ dữ liệu nào lên board chung với lý do “để mọi người theo dõi”.

### Phân loại thông tin theo quyền

| Thông tin | Cách xử lý |
| --- | --- |
| Product Goal, PBI không nhạy cảm, trạng thái chung | Cho nhóm và stakeholders có liên quan xem. |
| Hợp đồng API, quyết định kiến trúc | Chia sẻ cho những nhóm chịu ảnh hưởng, dùng quyền truy cập phù hợp. |
| Dữ liệu học viên, điểm cá nhân, token, secret | Không đưa vào chat/ticket công khai; ẩn hoặc dùng dữ liệu thử hợp lệ. |
| Sự cố bảo mật | Theo kênh/incident record có quyền hạn, chỉ chia thông tin cần thiết rộng hơn. |
| Vấn đề sức khỏe, nghỉ phép cá nhân, feedback nhân sự | Bảo vệ riêng tư; chỉ công bố tác động capacity cần thiết khi phù hợp. |
| Dữ liệu hợp đồng/tuân thủ | Theo chính sách lưu vết, phân loại và truy cập được tổ chức quy định. |

### Sự an toàn tâm lý giúp trạng thái trung thực

Nếu người thông báo blocker bị trách phạt trước nhóm, mọi người sẽ chuyển blocker thành “đang làm”. Nếu người hỏi “quy tắc này nghĩa là gì?” bị coi là thiếu năng lực, họ có thể giữ im lặng tới khi lỗi tích hợp xảy ra.

Nhóm nên:

- Phân biệt sự kiện được xác minh, suy đoán và đề xuất.
- Coi việc nêu rủi ro sớm là hành vi có ích.
- Không dùng điểm cá nhân/online status để chấm năng lực.
- Thảo luận lỗi theo cơ chế hệ thống và cách kiểm chứng.
- Tôn trọng phản biện của người không dự cuộc họp.
- Giữ quyền truy cập phù hợp, không biến transparency thành công khai dữ liệu riêng.
- Hỏi và xác nhận ngữ nghĩa thay vì dựa vào định kiến địa điểm/văn hóa.

**Một hệ thống có bảng công khai đẹp nhưng người trong nhóm sợ nói thật không có minh bạch đáng tin.**

## 22. Viết để người không dự cuộc họp vẫn hiểu

Thông tin dễ tìm thôi chưa đủ nếu chứa chữ viết tắt, giả định hoặc hình ảnh khó đọc.

### Nguyên tắc thiết kế tài liệu và thông báo

- Tiêu đề nêu **vấn đề hoặc quyết định**, không chỉ “Update”.
- Mở rộng chữ viết tắt quan trọng ở lần dùng đầu.
- Tách **sự kiện đã kiểm chứng** khỏi **giả thuyết**.
- Có link tới test, PR, PBI, ADR và contract liên quan.
- Dùng ngày và timezone rõ; tránh “hôm qua”, “ngày mai” trong thông báo để lại lâu.
- Với sơ đồ, thêm mô tả văn bản ngắn để người đọc bằng công cụ hỗ trợ vẫn hiểu.
- Mỗi hành động có owner và tiêu chí hoàn tất.
- Ghi giới hạn/ngữ cảnh cần thiết để người mới không phải hỏi lại mọi chuyện.
- Không lạm dụng @everyone hoặc tin nhắn nhỏ tạo nhiều ngắt quãng.
- Có cách góp ý bất đồng bộ cho người ở múi giờ khác.

### Tránh định kiến ngôn ngữ

Nhóm có thể chọn một ngôn ngữ chung cho quyết định kỹ thuật, nhưng phải cho phép người chưa tự tin **hỏi lại hoặc tóm tắt theo cách hiểu của họ**. Trong quyết định quan trọng, việc mỗi nhóm diễn đạt lại kết quả cần thực hiện có thể phát hiện khác biệt ý nghĩa sớm.

### Tránh tài liệu quá dài không ai đọc

Một decision log 10 dòng được dùng thường xuyên có thể tốt hơn một đặc tả 100 trang không có người cập nhật. Hãy viết **vừa đủ để người khác hành động đúng**, rồi tăng chi tiết khi có rủi ro hoặc phạm vi lớn.

## 23. Đo hiệu quả minh bạch bằng khả năng giao việc và học hỏi

Không nên đo “minh bạch” bằng số tin nhắn mỗi ngày hoặc số giờ online. Nên dùng những tín hiệu **toàn hệ thống**:

| Góc nhìn | Tín hiệu có thể dùng | Tránh diễn giải máy móc |
| --- | --- | --- |
| **Mục tiêu** | Sprint Goal có kết quả có ý nghĩa, tiến bộ hướng Product Goal. | Không ép luôn đạt 100% mục tiêu dễ để số đẹp. |
| **Dòng công việc** | Throughput, cycle time, WIP, work item age. | Số ticket Done không đồng nghĩa giá trị hay năng suất cá nhân. |
| **Phụ thuộc** | Blocked time, số PBI chờ hợp đồng hoặc quyết định quá lâu. | Đừng xếp hạng nhóm “trả lời chậm” nếu chưa xét loại việc và rủi ro. |
| **Quyết định** | Thời gian từ proposal đủ rõ đến quyết định, số lần phải mở lại vì thiếu bối cảnh. | Quyết định quan trọng không nhất thiết nhanh như quyết định nhỏ. |
| **Chất lượng** | Lỗi tích hợp, vi phạm DoD, lỗi phân quyền, tỷ lệ rollback phù hợp. | Không hạ kiểm thử để rút cycle time. |
| **Phản hồi sản phẩm** | Thời gian từ Done tới phản hồi hữu ích, task success, phản hồi định tính. | Nhiều release không tự chứng minh nhiều giá trị. |
| **Khả năng phối hợp** | Người mới tìm được thông tin không, mức phụ thuộc một người. | Không biến khảo sát trải nghiệm thành bảng chấm điểm cá nhân. |

### Ví dụ tính blocked time

Một nhóm ghi thời gian blocked của 10 PBI liên nhóm đã hoàn tất (đơn vị ngày làm việc):

| PBI | Blocked time |
| --- | ---: |
| A | 0,5 |
| B | 1,0 |
| C | 0,0 |
| D | 2,0 |
| E | 1,5 |
| F | 0,0 |
| G | 3,0 |
| H | 1,0 |
| I | 0,5 |
| J | 1,5 |

Tổng:

\[
0{,}5+1+0+2+1{,}5+0+3+1+0{,}5+1{,}5=11\ \text{ngày làm việc}
\]

Trung bình:

\[
\frac{11}{10}=1{,}1\ \text{ngày làm việc/PBI}
\]

Đây là **thống kê mô tả**, không phải cam kết PBI tiếp theo bị chặn 1,1 ngày. Cần xem phân bố: một PBI chờ 3 ngày, hai PBI không chờ. Hãy điều tra nguồn chờ dài: hợp đồng không rõ, người duyệt quá tải hay thiếu cơ chế thay thế người vắng mặt.

**Lưu ý:** tổng thời gian blocked của các PBI **không bằng thời gian lịch toàn dự án** vì nhiều PBI có thể diễn ra song song.

### WIP và Little's Law

Trong hệ thống đủ ổn định, ranh giới đo nhất quán, có quan hệ gần đúng:

\[
\overline{WIP} \approx \lambda \times \overline{CycleTime}
\]

Ở đây \(\lambda\) là **throughput trung bình** theo cùng đơn vị thời gian. Nếu WIP tăng mà throughput không tăng, cycle time có thể dài hơn. Công thức giúp tìm hiểu luồng, **không phải một cam kết thời gian cho từng Developer**.

## 24. Ví dụ xuyên suốt: nhóm phân tán giao tính năng “Học tiếp”

Giả sử một sản phẩm học Java được phát triển bởi:

- **Product/UX** ở Việt Nam.
- **Learning Developers** ở Việt Nam và châu Âu.
- **Identity, QA và vận hành** có người ở Bắc Mỹ.

Đây là tình huống sư phạm; không áp đặt mỗi địa điểm phải là một phòng ban cố định.

### Mục tiêu chung

**Product Goal:**

> “Giúp học viên đang học có thể tìm lại bài dở và tiếp tục thuận tiện, với dữ liệu tiến độ chính xác và được bảo vệ.”

**Sprint Goal:**

> “Học viên có quyền mở lại một video từ vị trí đã lưu qua các phiên đăng nhập, với hành vi khi không có dữ liệu và khi lỗi rõ ràng.”

**Chưa làm trong lát đầu:** đồng bộ offline phức tạp, AI gợi ý và thống kê toàn khóa. Những hướng này có thể vào Product Backlog để ưu tiên sau phản hồi.

### Các PBI cần liên kết

| PBI | Outcome hoặc hợp đồng | Phụ thuộc | Điều kiện Done |
| --- | --- | --- | --- |
| **LEARN-41** | Lưu/khôi phục vị trí video qua phiên. | Identity token policy, dữ liệu tiến độ. | Positive/negative integration tests, DoD. |
| **LEARN-42** | Đường vào “Học tiếp” cho bài đang học. | Dữ liệu LEARN-41 đúng. | UI có thể dùng, accessibility checks, DoD. |
| **ID-12** | Hợp đồng kiểm tra quyền tiến độ. | Identity owner và Learning consumer. | Contract được thống nhất, kiểm thử. |
| **OBS-05** | Quan sát lỗi lưu/đọc mà không lộ dữ liệu riêng. | Chính sách telemetry. | Kiểm tra log/metric thích hợp. |

### Bản cập nhật xuyên múi giờ

~~~text
SPRINT STATUS — YYYY-MM-DD
Goal: Học viên có quyền mở lại video qua phiên đăng nhập.

DONE:
  ID-12: contract v2 có hiệu lực, negative test đạt.

IN PROGRESS:
  LEARN-41: unit tests đạt, đang tích hợp với UI.
  LEARN-42: UI code đã review, chờ kiểm tra trên API thật.

BLOCKED/RISKS:
  OBS-05: telemetry chưa được xác nhận không lộ dữ liệu.
  Nếu chưa đạt điều kiện này, release sẽ chưa đủ an toàn.

DECISION:
  DEC-018: Chỉ báo "Đã lưu" sau xác nhận API.

NEXT:
  Learning/QA hoàn tất integration và DoD.
  PO chuẩn bị nhóm thử, chưa mở release khi thiếu điều kiện.
~~~

Người ở địa điểm khác có thể xác định **mục tiêu, sự thật, rủi ro, quyết định và bước tiếp theo**.

### Acceptance criteria có thể kiểm tra

~~~gherkin
Feature: Tiếp tục video giữa các phiên đăng nhập

Scenario: Người học có quyền khôi phục vị trí
  Given người học có quyền xem "Bài Java A"
  And hệ thống đã lưu vị trí 05:20 cho người học trong bài đó
  When người học mở lại bài ở một phiên đăng nhập khác
  Then video có thể tiếp tục từ vị trí đã lưu theo quy tắc đã thống nhất
  And không tiết lộ tiến độ của tài khoản khác

Scenario: Lưu tiến độ không thành công
  Given người học có quyền xem video
  And dịch vụ ghi tiến độ không thể hoàn tất thao tác
  When ứng dụng gửi vị trí mới
  Then giao diện không báo sai rằng đã lưu thành công
  And hiển thị trạng thái và cách xử lý lỗi phù hợp

Scenario: Không có quyền đọc tiến độ
  Given một tài khoản không được xem tiến độ của học viên khác
  When tài khoản đó yêu cầu đọc tiến độ người học khác
  Then hệ thống từ chối theo chính sách
  And không tiết lộ dữ liệu tiến độ riêng tư

Scenario: Chưa có vị trí lưu
  Given người học được phép xem bài học
  And chưa từng có vị trí lưu cho bài đó
  When người học mở bài học
  Then video bắt đầu từ đầu
  And không hiển thị thông báo đã khôi phục
~~~

Gherkin giúp **làm rõ hành vi**; nó không thay thế các lớp kiểm thử tích hợp, bảo mật, hiệu năng hoặc DoD thích hợp.

### Từ Increment tới phản hồi

Sau khi Increment thực sự Done, nhóm có thể mở cho một lớp học viên được cấp quyền theo chính sách release. Quan sát:

- Người học có tìm được nút “Học tiếp”?
- Vị trí được khôi phục có chính xác giữa các phiên?
- Thông báo “Đang lưu” có gây hiểu nhầm?
- Có lỗi truy cập trái quyền, dữ liệu hỏng hoặc sự cố không?
- Người học muốn đồng bộ offline hay chỉ cần đường vào bài dễ tìm hơn?

Kết quả đi vào Product Backlog. Một bản report từ địa điểm thử nghiệm **không phải đích cuối của feedback**.

## 25. Những anti-patterns khi “thông tin nhiều” nhưng phối hợp vẫn kém

| Anti-pattern | Hậu quả | Cách cải thiện |
| --- | --- | --- |
| **Quyết định chỉ ở chat riêng** | Người vắng mặt làm theo hiểu biết cũ. | Decision log/ADR có trạng thái và liên kết. |
| **Mỗi địa điểm có backlog ưu tiên riêng** | Sản phẩm bị chia thành các hướng khác nhau. | Nguồn Product Backlog có thẩm quyền. |
| **“90% Done” thay DoD** | Báo cáo xanh nhưng Increment chưa dùng được. | Trạng thái dựa trên điều kiện và bằng chứng. |
| **Mọi ticket cùng In Progress** | Không biết điểm nghẽn và việc gần Done. | WIP control, blocked policy, chú trọng hoàn tất. |
| **Daily Scrum là buổi điểm danh** | Developers không kiểm tra Sprint Goal. | Trạng thái trên bảng, sự kiện tập trung inspection/adaptation. |
| **Cập nhật dài để chứng minh hoạt động** | Mọi người đọc nhiều nhưng quyết định chậm. | Tóm tắt thay đổi, rủi ro, bằng chứng và next action. |
| **Họp luôn theo múi giờ trụ sở** | Người ở địa điểm khác bị loại khỏi quyết định. | Luân phiên và bình luận bất đồng bộ trước/sau. |
| **Không owner cho proposal** | Thảo luận không kết thúc. | Gắn quyền chốt, thời điểm và escalation. |
| **Im lặng được coi là phê duyệt** | Việc có rủi ro được triển khai thiếu thẩm quyền. | Phân biệt xin ý kiến với phê duyệt bắt buộc. |
| **Dùng giờ online làm KPI** | Hoạt động hình thức, thiếu niềm tin. | Đo flow, chất lượng, outcome. |
| **Mọi vấn đề đều tạo cuộc họp đông người** | Phân mảnh thời gian và tăng chờ. | Async trước, đồng bộ đúng nơi cần quyết định nhanh. |
| **Tin nhắn nào cũng gắn urgent** | Mất khả năng phân biệt sự cố thật. | Chính sách mức khẩn và kênh incident. |
| **Đổ lỗi khi blocked** | Người ta giấu rủi ro. | Xử lý phụ thuộc như vấn đề dòng công việc. |
| **Done khi chưa kiểm tra quyền** | Lộ dữ liệu hoặc lỗi khi release. | DoD và negative tests phù hợp. |
| **Báo Done = Released** | Stakeholder tưởng người dùng đã có giá trị. | Phân biệt Done, Deploy, Release, Feedback. |
| **Dữ liệu nhạy cảm trong ticket** | Rủi ro bảo mật, riêng tư. | Quyền truy cập và bằng chứng đã che thông tin. |
| **ADR không trạng thái/ngày hiệu lực** | Không biết quyết định nào đang áp dụng. | Version, Accepted/Superseded, owner và scope. |
| **Ngoại lệ “tạm” không bao giờ hết hạn** | Guardrail bị phá lâu dài. | Ghi thời hạn, owner và điều kiện xem lại. |
| **Chuyển ca không handoff** | Điều tra lặp, blocked tăng. | Bằng chứng, next action, owner, rủi ro. |
| **Goal chỉ là points/ticket** | Tối ưu số lượng output thay vì giá trị. | Kết nối mục tiêu người dùng và DoD. |

## 26. Thử cải tiến trong hai Sprint: minh bạch quyết định liên nhóm

Một nhóm nhận thấy PBI thường bị chặn một đến ba ngày khi thay API. Quyết định nằm trong chat, và consumer phát hiện thay đổi muộn.

### Giả thuyết

> “Nếu mỗi thay đổi hợp đồng liên nhóm có owner, decision log ngắn và contract tests liên kết từ PBI, blocked time do thiếu thông tin sẽ giảm mà lỗi tích hợp sau merge không tăng.”

### Thiết kế thí nghiệm

| Thành phần | Cách làm minh họa |
| --- | --- |
| **Phạm vi** | Learning và Identity, những PBI thay hợp đồng quyền. |
| **Thay đổi** | Dependency card, quyết định có trạng thái, link contract tests. |
| **Giữ nguyên** | Sprint Goal, DoD, kiểm thử quyền và nghĩa vụ tổ chức. |
| **Người theo dõi** | Owner hợp đồng và người hỗ trợ cải tiến luồng. |
| **Số đo flow** | Blocked time vì contract, work item age. |
| **Guardrail** | Không tăng lỗi tích hợp, sự cố quyền hoặc rework. |
| **Phản hồi định tính** | Người ở các múi giờ có tìm được quyết định và next action? |
| **Xem lại** | Sau hai Sprint hoặc khi có đủ PBI tương tự để quan sát. |
| **Hành động** | Giữ, rút gọn, điều chỉnh hoặc hoàn tác chính sách. |

### Điều gì có thể gây sai lệch?

- Hai giai đoạn có loại việc/độ phức tạp khác nhau.
- Cùng lúc đổi pipeline hoặc người chịu trách nhiệm.
- Tăng/giảm incident làm thay capacity.
- Cách ghi blocked time thay đổi, dữ liệu không còn cùng định nghĩa.
- Mẫu nhỏ không đủ kết luận nhân quả.

**Cải tiến thật** không chỉ là blocked time giảm; cần xem Increment có tới người dùng sớm hơn, chất lượng ổn và quyết định có hiệu quả hơn không.

## 27. Working agreement mẫu cho nhóm phân tán

Một thỏa thuận ngắn có thể giúp người mới tham gia không phải hỏi “nhóm mình làm thế nào?” ở mười kênh khác nhau.

~~~text
WORKING AGREEMENT — phiên bản / ngày hiệu lực / owner

1. MỤC TIÊU:
   Product Goal và Sprint Goal / mục tiêu luồng nằm ở đâu?
   Ai cập nhật ưu tiên? Khi nào thông báo thay đổi?

2. CÔNG VIỆC:
   Board chính, trạng thái, WIP, blocked policy, DoD.
   Acceptance criteria và link bằng chứng Done.

3. QUYẾT ĐỊNH:
   Loại nào local, loại nào liên nhóm, loại nào cần approval?
   RFC/ADR/decision log lưu ở đâu?
   Trạng thái Proposed/Accepted/Superseded và mốc xem lại.

4. GIAO TIẾP:
   Async cho nội dung nào; khi nào họp ngắn?
   Kênh review, dependency, incident và phản hồi stakeholder.

5. MÚI GIỜ:
   Timezone chuẩn trong lịch; giờ liên hệ thông thường.
   Luân phiên giờ họp khó; quy tắc không đòi trả lời ngoài giờ.

6. HANDOFF:
   Mục tiêu, trạng thái xác minh, bằng chứng,
   next action, owner và rủi ro.

7. RELEASE:
   DoD, CI, policy phát hành, Done/Deployed/Released/Feedback.
   Không bỏ điều kiện an toàn để rút thời gian.

8. ĐO LƯỜNG:
   Cycle time, WIP, blocked, chất lượng và phản hồi người dùng.
   Không xếp hạng bằng online time hoặc points cá nhân.

9. CẢI TIẾN:
   Khi nào xem lại thỏa thuận, ai thay đổi và lưu phiên bản?
~~~

Thỏa thuận có ích khi **ngắn, có thể tìm, còn hiệu lực và được dùng**. Nếu thành biểu mẫu phải điền cho mọi thao tác nhỏ nhưng không tạo quyết định, cần đơn giản hóa.

## 28. Bài tập tình huống: một Sprint thiếu minh bạch

Một nhóm phân tán phát triển tính năng **đặt lịch tư vấn học Java**. Product Owner ở Việt Nam, Developers làm tại hai múi giờ, QA và vận hành ở nơi khác. Nhóm tuyên bố dùng Scrum đầy đủ, Sprint hai tuần.

**Dữ liệu bài tập:**

1. Product Goal trên slide là “Trở thành nền tảng học tốt nhất”; không có kết quả cụ thể.
2. Sprint Goal được ghi “Đóng 25 story points”.
3. Board có bảy PBI In Progress, hai PBI Done nhưng một trong hai chưa qua kiểm thử đặt lịch cạnh tranh.
4. PO đổi ưu tiên sau cuộc gọi nhỏ mà Product Backlog không cập nhật.
5. Nhóm API đổi phản hồi lỗi đặt lịch trùng từ HTTP 409 sang HTTP 200 kèm mã lỗi trong body; UI không được thông báo.
6. Một Developer viết “backend done” nhưng endpoint còn lỗi phân quyền.
7. Người ở múi giờ khác mở chat thấy 60 tin nhắn, không biết điều nào là quyết định.
8. Sự cố production “đặt lịch trùng” chỉ được nhắn vào channel thường; không có incident owner.
9. Quản lý yêu cầu ảnh chụp trạng thái online mỗi hai giờ.
10. Build đã triển khai, nhưng feature flag chưa mở; báo cáo nói “đã phát hành”.
11. Nhóm không theo dõi blocked time, cycle time và tuổi work item.
12. Retrospective trước nêu chờ review quá lâu, nhưng không có người phụ trách cải tiến.

### Câu hỏi

1. Xác định ít nhất **sáu điểm thiếu minh bạch**, nêu tác động tới người học hoặc nhóm.
2. Viết lại **Product Goal** và **Sprint Goal** theo kết quả có thể kiểm tra.
3. Thiết kế một **board** có trạng thái, blocked policy và ít nhất một WIP limit minh họa.
4. PBI nào **không được gọi Done** nếu chưa kiểm thử đúng? Vì sao?
5. Thiết kế quyết định API 409/200: owner, consumer, contract tests, trạng thái, kế hoạch tương thích.
6. Viết một **cập nhật async** để người ở múi giờ khác biết next action.
7. Thiết kế handoff cho sự cố đặt lịch trùng với kênh khẩn và thẩm quyền phù hợp.
8. Phân biệt **Done, Deployed, Released** trong tình huống.
9. Chọn hai flow metrics, hai guardrails chất lượng và một outcome người học.
10. Trả lời đề xuất theo dõi màn hình online theo mục tiêu minh bạch Agile.
11. Chọn **một thử nghiệm cải tiến nhỏ** cho Sprint tới và dữ liệu để đánh giá.
12. Nếu nhóm bỏ hoàn toàn Daily Scrum vì khó trùng giờ mà vẫn gọi Scrum đầy đủ, cần làm rõ điều gì?

## 29. Hướng giải tham khảo

### 29.1. Vấn đề và mục tiêu

| Vấn đề | Hậu quả |
| --- | --- |
| Product Goal quá mơ hồ và Sprint Goal bằng points. | Không biết trải nghiệm học viên nào cần có. |
| Done khi chưa kiểm thử cạnh tranh. | Trạng thái sai, nguy cơ đặt lịch trùng. |
| Thứ tự backlog đổi trong cuộc gọi riêng. | Mỗi múi giờ làm theo một ưu tiên. |
| API đổi status mà không có quyết định/hợp đồng. | UI có thể coi lỗi là thành công. |
| “Backend done” khi chưa qua quyền. | Nguy cơ lộ dữ liệu hoặc thao tác trái phép. |
| Chat quá nhiều nhưng không có quyết định có hiệu lực. | Người đến sau phải đoán, rework. |
| Không có incident owner. | Sự cố nghiêm trọng chậm phản ứng. |
| Bật feature flag chưa có mà báo release. | Stakeholder tưởng người học đã sử dụng. |
| Không có flow metrics. | Không nhìn điểm chờ và WIP. |
| Giám sát online. | Khuyến khích hiện diện hình thức thay vì kết quả. |

**Product Goal mẫu:**

> “Học viên có thể đặt lịch tư vấn Java đáng tin cậy, không gặp tình trạng lịch trùng hoặc truy cập sai quyền.”

**Sprint Goal mẫu:**

> “Học viên có quyền chọn một khung giờ hợp lệ, đặt lịch không trùng kể cả khi có yêu cầu cạnh tranh và nhận phản hồi xác nhận chính xác.”

### 29.2. Board và điều kiện Done

~~~text
Ready -> Develop (WIP <= 3) -> Review (WIP <= 2) -> Verify -> Done

Blocked:
  Nêu nguyên nhân, bằng chứng, owner, next action và checkpoint.

Definition of Done:
  - Không cho phép đặt lịch trùng trái quy tắc khi có yêu cầu cạnh tranh.
  - Kiểm tra quyền thao tác và xem dữ liệu lịch.
  - API/UI xử lý đúng hợp đồng success/error.
  - Integration/regression tests phù hợp đạt.
  - Không báo đặt thành công khi ghi dữ liệu thất bại.
~~~

Một PBI chưa qua kiểm thử cạnh tranh cần được **đánh dấu trạng thái chưa Done**, nếu điều kiện đó thuộc DoD/tiêu chí bắt buộc. Không nên hạ DoD chỉ để giữ báo cáo xanh.

### 29.3. Quyết định API 409/200

- **Nguồn:** versioned API contract do nhóm API sở hữu, UI là consumer.
- **Vấn đề:** đổi 409 thành 200 có thể khiến UI báo thành công giả.
- **Lựa chọn:** giữ 409 với body chuẩn, hoặc đổi hợp đồng có kế hoạch chuyển đổi an toàn; cần đánh giá đầy đủ semantics.
- **Thẩm quyền:** người có quyền chốt hợp đồng theo tổ chức, tham vấn UI, QA, PO và người liên quan.
- **Kiểm chứng:** contract tests và acceptance tests cho trường hợp trùng lịch.
- **Trạng thái:** Proposed khi chưa được chốt; Accepted có hiệu lực/version sau khi được duyệt.
- **Rollout:** bảo đảm tương thích consumer hoặc chuyển version theo giai đoạn, giám sát lỗi.

Không thể chỉ nói “đã đổi” và giả định các nhóm khác hiểu giống nhau.

### 29.4. Async update mẫu

~~~text
Goal: Học viên đặt lịch đúng, không trùng và nhận xác nhận hợp lệ.

Status:
  BOOK-17 đang Verify, test concurrent booking thất bại.
  PBI chưa Done và không đủ điều kiện release.

Blocked:
  Hợp đồng API conflict status chưa được chốt.
  Link proposal + failing contract test.

Next:
  API owner và UI consumer thống nhất hợp đồng.
  QA bổ sung negative test; Developers sửa rồi xác minh DoD.

Risk:
  Sprint Goal gặp rủi ro; PO đã được thông báo.
  Không mở tính năng cho học viên khi điều kiện chất lượng chưa đạt.
~~~

### 29.5. Incident và chỉ số

Lỗi đặt lịch trùng cần được phân loại theo mức nghiêm trọng, có **incident record, người điều phối và kênh trực phù hợp**. Handoff nêu tác động, những hệ thống liên quan, bằng chứng đã loại dữ liệu nhạy cảm, tình trạng hiện tại và việc tiếp theo. Không yêu cầu mọi người online ngoài giờ nếu họ không thuộc chính sách trực.

- **Flow:** cycle time Started → Done, blocked time chờ hợp đồng/review, xem WIP khi cần.
- **Guardrail:** không tạo lịch trùng trái quy tắc, không thao tác lịch trái quyền hoặc xác nhận sai thành công.
- **Outcome:** tỷ lệ người học hoàn tất đặt một lịch tư vấn hợp lệ trong bài thử/luồng thật có định nghĩa rõ.
- **Release:** deployed nhưng flag chưa mở **chưa phải Released**; lỗi DoD còn tồn tại **chưa phải Done**.

Đề xuất giám sát online nên được thay bằng **mục tiêu rõ, board minh bạch, DoD, blocked policy và flow/quality metrics**.

### 29.6. Một thử nghiệm cải tiến nhỏ

Thử trong hai Sprint: mọi thay đổi API có consumer phải có **decision log ngắn, owner và contract tests liên kết từ PBI**. Quan sát blocked time, lỗi tích hợp, cảm nhận người thực hiện; giữ điều kiện bảo mật và DoD.

Nếu nhóm tuyên bố Scrum đầy đủ, **Daily Scrum là sự kiện cốt lõi**, 15 phút của Developers để kiểm tra Sprint Goal và thích ứng Sprint Backlog. Có thể đổi cách tiến hành và thêm async prep. Nếu bỏ hẳn mà vẫn gọi Scrum đầy đủ, cần mô tả cách làm trung thực hơn; mô hình khác có thể hữu ích nhưng không còn đủ cấu trúc Scrum Guide.

## 30. Tự kiểm tra kiến thức

**Câu 1.** Minh bạch có nghĩa mọi người phải công khai trạng thái online liên tục không?

**Đáp án:** Không. Minh bạch cung cấp thông tin đúng, kịp thời, có ngữ cảnh và tra cứu được cho quyết định, trong giới hạn riêng tư/bảo mật; không phải theo dõi hiện diện từng phút.

**Câu 2.** Vì sao “90% Done” không đủ giúp nhóm khác quyết định bước tiếp?

**Đáp án:** Không biết phần nào được kiểm chứng, DoD đã đạt chưa, blocker nào còn tồn tại và ai cần hành động. Cần trạng thái thật, bằng chứng và next action.

**Câu 3.** Goal “Đóng 20 points” có đủ mô tả giá trị người dùng?

**Đáp án:** Không. Points là kỹ thuật ước lượng nội bộ tùy chọn; mục tiêu sản phẩm/Sprint nên hướng tới kết quả dùng được có ý nghĩa.

**Câu 4.** Quyết định trong chat riêng có thể dẫn tới điều gì?

**Đáp án:** Người vắng mặt dùng thông tin cũ, tạo code không tương thích hoặc thảo luận lại cùng vấn đề. Cần bản ghi quyết định có thẩm quyền và liên kết.

**Câu 5.** RFC ở trạng thái Proposed có thể coi là Approved vì không ai phản đối?

**Đáp án:** Không tự động. Cần đúng người có thẩm quyền, và với phê duyệt bắt buộc thì im lặng không đồng nghĩa được phép.

**Câu 6.** Khi nào nên đổi từ comment async sang trao đổi đồng bộ?

**Đáp án:** Khi hiểu sai lặp lại, cần quyết định nhanh hoặc đang xảy ra incident. Sau cuộc gọi vẫn ghi quyết định và hành động rõ.

**Câu 7.** Bàn giao qua múi giờ tối thiểu cần gì?

**Đáp án:** Mục tiêu, trạng thái đã xác minh, bằng chứng, bước tiếp, rủi ro, owner và đường phản hồi/chuyển cấp.

**Câu 8.** Daily Scrum có bắt buộc mỗi người trả lời ba câu hỏi cố định?

**Đáp án:** Không. Scrum xác định mục đích và timebox; định dạng linh hoạt. Nó vẫn là sự kiện của Developers trong Scrum đầy đủ, không phải cuộc điểm danh cho quản lý.

**Câu 9.** Một PBI đã merge nhưng kiểm thử quyền thất bại có gọi Done được không?

**Đáp án:** Không khi chưa đáp ứng DoD. Phải xử lý và kiểm chứng hành vi trước.

**Câu 10.** Done, Deployed và Released khác nhau thế nào?

**Đáp án:** Done là Increment đạt DoD; Deployed là có trên môi trường; Released là mở cho nhóm người dùng cụ thể. Phản hồi được quan sát riêng.

**Câu 11.** Có nên dùng blocked time để xếp hạng “địa điểm nào làm chậm nhất” không?

**Đáp án:** Không. Blocked time là tín hiệu của luồng; phải xem loại việc, thẩm quyền, mức khẩn, phụ thuộc và capacity trước khi cải tiến.

**Câu 12.** Vì sao liên kết nguồn có thẩm quyền tốt hơn nhiều bản sao nhập tay?

**Đáp án:** Giảm thông tin lệch phiên bản, dễ kiểm tra bằng chứng và biết trạng thái hiện hành.

**Câu 13.** Hai nhóm hiểu khác về “hoàn thành bài học” thì phải làm gì?

**Đáp án:** Làm rõ người sở hữu quy tắc nghiệp vụ, ghi quyết định có hiệu lực và kiểm thử ví dụ hành vi; tạo thêm ticket không tự giải quyết sự khác biệt nghĩa.

**Câu 14.** Khi quyết định cũ không còn phù hợp, nên xóa lịch sử không?

**Đáp án:** Không nên. Tạo quyết định mới thay thế và giữ bối cảnh cũ để giải thích cấu trúc và tránh lặp lỗi.

**Câu 15.** Ít họp hơn nhưng lỗi tích hợp tăng và người mới khó tìm quyết định có phải cải tiến không?

**Đáp án:** Chưa có cơ sở. Phải đánh giá flow, chất lượng và khả năng phối hợp; có thể cần bổ sung thông tin hoặc thay cách trao đổi.

## 31. Checklist duy trì minh bạch

### Mục tiêu

- [ ] Product Goal/mục tiêu sản phẩm hiện hành dễ tìm và có owner rõ.
- [ ] Sprint Goal/mục tiêu ngắn hạn nêu kết quả người dùng, không chỉ points.
- [ ] Product Backlog được cập nhật ở nguồn chính khi ưu tiên thay đổi.
- [ ] Người ở địa điểm khác hiểu điều đang ưu tiên và điều chủ động chưa làm.
- [ ] Phản hồi người dùng có đường quay lại quyết định và backlog.

### Công việc

- [ ] Board có thẩm quyền, trạng thái/Definition of Workflow rõ.
- [ ] Ready, Started, Review, Verify, Done có cùng cách hiểu.
- [ ] PBI có acceptance criteria và liên kết kiểm chứng cần thiết.
- [ ] Blocked có nguyên nhân, owner, next action, checkpoint và escalation.
- [ ] Có WIP control để hỗ trợ hoàn tất, không chỉ mở thêm việc.
- [ ] DoD chung được giữ, không hạ ngầm qua múi giờ hoặc nhóm.
- [ ] Không dùng tỷ lệ “gần xong” làm bằng chứng Done.

### Quyết định

- [ ] Quyết định liên nhóm có người có thẩm quyền chốt.
- [ ] Proposed, Accepted, Superseded được phân biệt.
- [ ] Bối cảnh, phương án, lý do, phạm vi và hiệu lực được ghi rõ.
- [ ] Người chịu ảnh hưởng có cơ hội tham vấn.
- [ ] Quyết định liên kết từ backlog, PR, contract hoặc test.
- [ ] Không coi im lặng là phê duyệt khi chính sách yêu cầu xác nhận.
- [ ] Có mốc xem lại và giữ lịch sử thay đổi.

### Múi giờ và giao tiếp

- [ ] Lịch và mốc phản hồi ghi timezone rõ.
- [ ] Họp khó được luân phiên hoặc có cách bình luận async công bằng.
- [ ] Cập nhật async ngắn, có bằng chứng và hành động chứ không chấm công.
- [ ] Việc khẩn có kênh incident, ca trực và owner theo thẩm quyền.
- [ ] Handoff có mục tiêu, trạng thái, bằng chứng, rủi ro và next action.
- [ ] Người vắng mặt tra cứu được kết luận mà không phải đọc toàn bộ chat.

### Chất lượng và cải tiến

- [ ] Phân biệt Done, Deployed, Released và Feedback Observed.
- [ ] Kiểm thử phân quyền/dữ liệu và rủi ro tương ứng đã đạt.
- [ ] Không đăng dữ liệu nhạy cảm vào ticket hoặc chat không đủ quyền.
- [ ] Theo dõi cycle time, WIP, blocked time và work item age khi hữu ích.
- [ ] Không xếp hạng theo online time, số tin nhắn hay points cá nhân.
- [ ] Thử một cải tiến nhỏ, quan sát kết quả và quyết định giữ/sửa/hoàn tác.

Checklist giúp nhóm **giảm bất định và phối hợp tốt hơn**, không phải tạo một cổng phê duyệt cho mọi cập nhật nhỏ. Nếu một trường thông tin không được dùng hoặc không tạo quyết định, hãy cân nhắc đơn giản hóa.

## 32. Những điều cần ghi nhớ

- **Minh bạch là thông tin đúng, kịp thời, đủ ngữ cảnh và tìm lại được**, không phải giám sát ai online.
- **Ba lớp phải kết nối:** mục tiêu người dùng, trạng thái công việc có bằng chứng và quyết định có hiệu lực.
- **Mỗi loại thông tin có nguồn có thẩm quyền**; chat và báo cáo nên liên kết đến nguồn, tránh bản sao lệch phiên bản.
- **Product Goal/Sprint Goal giúp tự chủ có định hướng**, không bị thay bằng chỉ tiêu ticket hoặc story points.
- **Board cần nhìn WIP, blocked, phụ thuộc, next action và Done đúng DoD**. Code xong không tự là Increment hoàn chỉnh.
- **Decision log/ADR phải có bối cảnh, phương án, thẩm quyền, hiệu lực và điều kiện xem lại**; không nhầm proposal với Accepted.
- **Async có ích khi đủ cấu trúc; đồng bộ hữu ích khi cần quyết định nhanh hoặc xử lý hiểu sai phức tạp**. Sau cuộc gọi vẫn ghi kết luận.
- **Bàn giao giữa múi giờ có bằng chứng và owner**; không để công việc trở thành “việc người khác”.
- **Tôn trọng múi giờ, quyền riêng tư, ngôn ngữ và an toàn tâm lý** giúp người ta dám nêu rủi ro sớm.
- **Scrum giữ inspection/adaptation với mục tiêu và DoD; Kanban làm rõ WIP/flow; XP tạo kiểm thử và tích hợp sớm**. Những cách làm bổ trợ cùng một mục tiêu giao Increment tin cậy.
- **Phân biệt Done, Deployed, Released và Feedback Observed** để biết người dùng đã thực sự nhận gì.
- **Đo cải tiến bằng flow, chất lượng và outcome**, không bằng lượng chat hay thời gian bật camera.

Minh bạch tốt không bắt mọi người viết nhiều hơn hoặc họp nhiều hơn. Nó giúp **người ở bất kỳ địa điểm nào cũng biết nhóm đang hướng tới giá trị gì, công việc thật sự ở đâu, quyết định nào đã có hiệu lực và hành động tiếp theo cần thực hiện**. Khi mục tiêu, luồng và quyết định được nối với bằng chứng, nhóm phân tán có thể giao phần mềm tăng dần, nhận phản hồi sớm và cải tiến liên tục mà không phải có mặt cùng một phòng hay cùng một múi giờ.
