# Minh bạch, kiểm tra và thích ứng trong Scrum

> **Thông điệp chính:** Scrum dựa trên **chủ nghĩa thực nghiệm (empiricism)**: hiểu biết hình thành từ trải nghiệm, và quyết định được đưa ra dựa trên điều đã quan sát. Ba trụ cột **minh bạch (transparency)**, **kiểm tra (inspection)** và **thích ứng (adaptation)** tạo thành một chu trình học hỏi để nhóm giao phần mềm có giá trị trong môi trường nhiều bất định. Không trụ cột nào có tác dụng trọn vẹn nếu tách khỏi hai trụ cột còn lại.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Giải thích ba trụ cột của Scrum và mối quan hệ của chúng với tư duy thực nghiệm, Lean và các giá trị Agile.
2. Phân biệt **minh bạch trạng thái sản phẩm/công việc** với việc chỉ có nhiều bảng biểu hoặc yêu cầu thành viên báo cáo liên tục.
3. Thực hiện **kiểm tra có mục đích**: so sánh kết quả quan sát với Product Goal, Sprint Goal, Definition of Done và phản hồi người dùng.
4. Chuyển kết quả kiểm tra thành **thích ứng có trách nhiệm**: điều chỉnh kế hoạch, Product Backlog, phạm vi, cách phối hợp hoặc thực hành kỹ thuật.
5. Nhận diện vai trò của **ba artifact, ba commitment và các sự kiện Scrum** đối với vòng phản hồi thực nghiệm.
6. Phân tích một tình huống phát triển phần mềm từ dữ kiện mới đến quyết định và kiểm chứng kết quả.
7. Vận dụng tư duy minh bạch–kiểm tra–thích ứng khi kết hợp Scrum với user story, Kanban, thực hành XP và các phép đo dòng công việc.

## 2. Vì sao Scrum cần ba trụ cột?

Giả sử một nhóm đang phát triển nền tảng học trực tuyến. Kế hoạch đầu Sprint là cải thiện luồng đăng ký và mở bài học đầu tiên. Sau vài ngày, nhóm phát hiện:

- Một số người học không nhận được email kích hoạt tài khoản kịp thời.
- Trên thiết bị di động, trang mở bài đầu tiên tải chậm.
- Nhóm đã đánh dấu nhiều ticket “hoàn thành”, nhưng một số tính năng chưa vượt qua kiểm thử tích hợp.

Nhóm có thể phản ứng theo hai hướng.

**Hướng thứ nhất:** giữ nguyên kế hoạch, ghi nhiều việc thành “Done” để báo cáo tiến độ đẹp, chờ đến cuối Sprint mới trình bày kết quả. Trên bảng công việc, nhóm có vẻ rất bận và hoàn thành nhiều việc, nhưng giá trị thực tế đối với người học có thể chưa tăng.

**Hướng thứ hai:** thể hiện rõ tình trạng tính năng và lỗi; cùng kiểm tra ảnh hưởng lên Sprint Goal; quyết định ưu tiên xử lý rủi ro quan trọng, điều chỉnh kế hoạch và kiểm chứng lại bằng Increment chạy được.

Hướng thứ hai thể hiện chu trình:

1. **Minh bạch:** biết điều gì thực sự đã hoàn thành, còn lỗi hoặc đang bị chặn.
2. **Kiểm tra:** đối chiếu thực tế với mục tiêu, chuẩn chất lượng và nhu cầu người học.
3. **Thích ứng:** thay đổi công việc hoặc cách làm dựa trên điều vừa học.

Scrum không hứa rằng yêu cầu sẽ không thay đổi hay mọi dự báo sẽ chính xác. Scrum tạo **nhịp kiểm tra và thích ứng đủ thường xuyên** để giảm thời gian nhóm tiếp tục đi sai hướng.

### 2.1. Chủ nghĩa thực nghiệm và tư duy Lean

Theo *Scrum Guide*, Scrum dựa trên **empiricism** và **Lean thinking**:

- **Empiricism:** kiến thức đến từ trải nghiệm; quyết định dựa vào quan sát. Khi chưa có bằng chứng, nhóm nêu rõ giả định và tìm cách kiểm chứng thay vì khẳng định chắc chắn.
- **Lean thinking:** tập trung vào những gì thiết yếu và giảm lãng phí. Trong bối cảnh sản phẩm, điều này có thể là bớt xây tính năng chưa cần, giảm công việc đang dở và rút ngắn thời gian nhận phản hồi.

Ba trụ cột giúp biến tư duy đó thành hành vi hằng ngày. Một quyết định không được đánh giá chỉ vì “làm đúng kế hoạch”, mà còn vì **kết quả thực tế có đưa sản phẩm tiến gần mục tiêu hay không**.

## 3. Mối quan hệ giữa minh bạch, kiểm tra và thích ứng

~~~mermaid
flowchart TD
    A["Minh bạch: nhìn thấy trạng thái thật và tiêu chuẩn chung"] --> B["Kiểm tra: đối chiếu với mục tiêu, chất lượng, phản hồi"]
    B --> C["Thích ứng: thay đổi quyết định hoặc cách thực hiện"]
    C --> D["Increment / kết quả / tín hiệu mới"]
    D --> A
    E["Scrum Values: Cam kết, Tập trung, Cởi mở, Tôn trọng, Can đảm"] -.-> A
    E -.-> B
    E -.-> C
~~~

| Thiếu trụ cột | Điều có thể xảy ra |
|---|---|
| **Thiếu minh bạch** | Nhóm kiểm tra dữ liệu sai hoặc thiếu; quyết định bị lạc hướng và rủi ro bị che giấu |
| **Thiếu kiểm tra** | Có dashboard, backlog và demo nhưng không so sánh với mục tiêu hay đặt câu hỏi về kết quả |
| **Thiếu thích ứng** | Cuộc họp tìm ra vấn đề lặp lại nhưng không ai thay đổi kế hoạch, chính sách hoặc cách triển khai |

**Kiểm tra mà không thích ứng có rất ít giá trị.** Ngược lại, đổi kế hoạch liên tục mà không có dữ kiện cũng không phải tư duy thực nghiệm. Chỉ khi có trạng thái đáng tin, cách kiểm tra đúng và quyền điều chỉnh phù hợp, nhóm mới học được từ công việc.

### 3.1. Ba trụ cột không phải ba bước chỉ diễn ra một lần

Nhóm không “minh bạch vào thứ Hai, kiểm tra vào thứ Tư, thích ứng vào thứ Sáu”. Chu trình có thể lặp lại ở nhiều nhịp:

- Trong một cuộc trao đổi ngắn khi phát hiện yêu cầu chưa rõ.
- Khi Developers kiểm tra tiến độ tới Sprint Goal tại Daily Scrum.
- Khi hệ thống CI báo kiểm thử thất bại và nhóm điều chỉnh cách tích hợp.
- Khi Sprint Review cho thấy người dùng không đạt kết quả mong đợi.
- Khi Sprint Retrospective phát hiện một điểm tắc lặp lại cần cải tiến.

Scrum có các sự kiện tạo nhịp kiểm tra và thích ứng, nhưng **không yêu cầu nhóm phải chờ đến một sự kiện chính thức** mới được xử lý vấn đề vừa phát sinh.

## 4. Trụ cột thứ nhất: Minh bạch (Transparency)

### 4.1. Minh bạch là gì?

Minh bạch nghĩa là **công việc và quá trình đang diễn ra được thể hiện đủ rõ cho người thực hiện lẫn người nhận kết quả**. Mọi người dùng những định nghĩa chung để hiểu trạng thái, chất lượng và rủi ro.

Ví dụ:

- Khi một Product Backlog Item (PBI) ở trạng thái “Done”, nó thực sự đáp ứng Definition of Done.
- Một hạng mục bị chặn bởi API bên ngoài được đánh dấu bị chặn, không để ở “Đang làm” mà không ai biết nguyên nhân.
- Sprint Goal được mô tả đủ rõ để Developers biết điều gì cần bảo vệ khi phạm vi có thay đổi.
- Product Owner và bên liên quan thấy kết quả sản phẩm đang hoạt động và những giới hạn còn tồn tại.

**Minh bạch không đồng nghĩa với công khai mọi dữ liệu cho mọi người.** Những thông tin cá nhân, bí mật kinh doanh hoặc dữ liệu bảo mật vẫn phải được xử lý theo quyền truy cập và chính sách thích hợp. Mục tiêu là **đủ thông tin đúng cho đúng người ra quyết định**, không phải thu thập và phát tán dữ liệu không kiểm soát.

### 4.2. Minh bạch khác với “có công cụ”

Một bảng Kanban, issue tracker hoặc biểu đồ burn-down chỉ hữu ích nếu phản ánh trạng thái thực. Chẳng hạn:

| Báo cáo bề ngoài | Tình trạng thật | Thực hành minh bạch hơn |
|---|---|---|
| “Tính năng đăng nhập đã xong.” | Có giao diện nhưng chưa kiểm thử quyền truy cập và lỗi đăng nhập | Ghi rõ phần đã thực hiện, phần chưa đạt DoD và rủi ro |
| “Không có blocker.” | Nhóm đang chờ quyết định từ người phụ trách nghiệp vụ | Đánh dấu blocker, người cần tham gia và thời gian đang chờ |
| “Sprint đạt 90%.” | Đếm ticket, không rõ mức tiến tới Sprint Goal | Kiểm tra trực tiếp khả năng đạt Sprint Goal và Increment thực |
| “Người học rất hài lòng.” | Mới có vài lời khen, chưa xem hành vi sử dụng | Tách phản hồi định tính khỏi bằng chứng hành vi và giới hạn mẫu |
| “Lỗi đã được xử lý.” | Có bản sửa trên nhánh cá nhân nhưng chưa tích hợp và xác nhận | Thể hiện rõ trạng thái mã, kiểm thử, triển khai và xác minh |

Minh bạch cần cả **định nghĩa** lẫn **hành vi trung thực**. Nếu một tổ chức thưởng/phạt theo số ticket Done, nhóm có thể cảm thấy áp lực đổi trạng thái sớm; khi đó dashboard ngày càng đẹp nhưng độ tin cậy giảm.

### 4.3. Ba artifact và ba commitment giúp minh bạch điều gì?

Scrum định nghĩa ba artifact chính, mỗi artifact có một commitment:

| Artifact | Commitment | Điều được minh bạch |
|---|---|---|
| **Product Backlog** | **Product Goal** | Công việc có thể cần làm để cải thiện sản phẩm và trạng thái tương lai đang hướng tới |
| **Sprint Backlog** | **Sprint Goal** | Vì sao Sprint có giá trị, việc được chọn và kế hoạch Developers dùng để đạt mục tiêu |
| **Increment** | **Definition of Done** | Điều gì thực sự đã tích hợp và đạt các tiêu chuẩn chất lượng cần thiết để được coi là hoàn thành |

Ba commitment khác nhau về vai trò nhưng đều giúp việc kiểm tra có ý nghĩa:

- **Product Goal:** đặt hướng dài hơn cho Product Backlog, tránh ưu tiên theo đề xuất rời rạc.
- **Sprint Goal:** tạo một mục tiêu gắn kết cho Sprint, hỗ trợ điều chỉnh phạm vi khi học thêm thông tin.
- **Definition of Done:** tạo chuẩn chung cho việc đánh giá một Increment; không để “Done” mang nghĩa khác nhau giữa các thành viên.

**Không nhầm:** user story, story point, epic hay biểu đồ burndown có thể hữu ích nhưng **không phải artifact hoặc commitment bắt buộc được Scrum Guide định nghĩa**. Nhóm chọn dùng chúng khi phục vụ mục đích thực tế.

### 4.4. Ví dụ minh bạch bằng Definition of Done

Một user story ghi:

> “Là người học mới, tôi muốn mở bài học đầu tiên từ màn chào mừng để không mất thời gian tìm qua nhiều menu.”

Giả sử giao diện và API đã được viết nhưng chưa xác minh trường hợp kết nối bị gián đoạn. Nếu Definition of Done yêu cầu kiểm thử hồi quy và kiểm soát lỗi cần thiết, story **chưa đạt Done**. Không nên coi đây là Increment hoàn thành chỉ vì nhánh mã đã được gộp.

Trong Scrum, phần việc không đáp ứng DoD **không được coi là một phần của Increment** và không nên được trình bày như công việc Done trong Sprint Review. Nó cần được xem xét lại trong Product Backlog cho công việc tiếp theo.

Minh bạch giúp nhóm phát hiện nhu cầu điều chỉnh sớm: thêm kiểm thử, giảm việc mới hoặc chia nhỏ phần còn lại.

### 4.5. Bảng thông tin tối thiểu có ích

Một bảng công việc minh họa:

~~~text
Sprint Goal:
  Người học mới có thể đăng ký và mở bài đầu tiên đáng tin cậy.

Đã đạt DoD:
  - Đăng ký tài khoản và đăng nhập với trường hợp chính

Đang thực hiện:
  - Mở bài đầu từ màn chào mừng (còn kiểm thử mất kết nối)

Bị chặn:
  - Ghi tiến độ bài đầu (đang chờ môi trường thử tích hợp)

Rủi ro đối với Sprint Goal:
  - Nếu việc ghi tiến độ chậm, cần ưu tiên luồng cơ bản đạt DoD

Quyết định cần trao đổi:
  - Nhóm có cần hoãn giao diện phụ để hoàn tất kiểm thử tích hợp không?
~~~

Bảng này không phải biểu mẫu chính thức của Scrum; nó minh họa cách hiển thị **mục tiêu, trạng thái, chất lượng và quyết định cần phối hợp** trong một nơi chung.

## 5. Trụ cột thứ hai: Kiểm tra (Inspection)

### 5.1. Kiểm tra điều gì và để làm gì?

**Inspection** là xem xét thường xuyên các artifact của Scrum và tiến độ hướng tới mục tiêu đã thống nhất để phát hiện sai lệch hoặc vấn đề không mong muốn. Kiểm tra phải **đủ thường xuyên và có mục đích**, nhưng không nên diễn ra dày đến mức làm gián đoạn chính công việc cần hoàn thành.

Kiểm tra có thể hướng tới bốn câu hỏi:

1. **Giá trị:** Increment có giải quyết vấn đề người dùng hay tạo khả năng học hỏi không?
2. **Chất lượng:** phần đã thực hiện có đáp ứng tiêu chuẩn và hoạt động đúng trong tình huống quan trọng không?
3. **Dòng công việc:** việc nào bị chặn, chờ lâu hoặc có nguy cơ không đạt mục tiêu?
4. **Giả định và kế hoạch:** chúng ta biết thêm điều gì khiến hướng đi hoặc cách phối hợp cần thay đổi?

Điểm cốt lõi là **so sánh trạng thái quan sát với mục tiêu hoặc chuẩn chung**. Xem hàng loạt số liệu mà không biết số liệu trả lời câu hỏi nào không tạo ra inspection hữu ích.

### 5.2. Phân biệt kiểm tra với giám sát cá nhân

| Kiểm tra theo tinh thần Scrum | Giám sát làm méo mục đích |
|---|---|
| “Increment đã đáp ứng DoD và phục vụ Sprint Goal đến đâu?” | “Ai làm ít ticket nhất?” |
| “Điểm tắc nào cần nhóm cùng tháo gỡ?” | “Tại sao hôm qua cá nhân này chưa cập nhật trạng thái đủ lần?” |
| “Người dùng gặp trường hợp khó hiểu nào khi dùng sản phẩm?” | “Tỷ lệ biểu đồ xanh đã đạt để trình bày với cấp trên chưa?” |
| “Phản hồi có buộc ta xem lại Product Backlog không?” | “Làm thế nào để giữ nguyên báo cáo thành tích dù dữ liệu mới không tốt?” |

Scrum đề cao nhóm **tự quản lý (self-managing)**, chịu trách nhiệm tạo Increment có giá trị. Việc kiểm tra có mục đích nên hỗ trợ nhóm ra quyết định, không biến Daily Scrum hoặc dashboard thành công cụ theo dõi vi mô từng người.

### 5.3. Tín hiệu định tính và định lượng

Không có chỉ số duy nhất chứng minh Scrum hoạt động tốt. Nhóm có thể xem:

| Tín hiệu | Câu hỏi cần trả lời | Giới hạn khi diễn giải |
|---|---|---|
| Phản hồi người dùng | Có điểm khó hiểu, nhu cầu mới hay vấn đề chưa được giải quyết không? | Phản hồi ít người không đại diện mọi phân khúc |
| Tỷ lệ người hoàn tất một tác vụ | Thay đổi có liên quan đến outcome mong đợi không? | Cần định nghĩa mẫu, thời gian và yếu tố khác ảnh hưởng |
| Lỗi nghiêm trọng sau phát hành | Sản phẩm có gây rủi ro về chất lượng không? | Tổng số lỗi không tự cho biết mức độ hoặc nguyên nhân |
| **WIP** | Nhóm có mở quá nhiều việc cùng lúc không? | WIP thấp không tự bảo đảm giá trị cao |
| **Cycle time / throughput** | Luồng công việc có đang bị nghẽn hoặc thay đổi bất thường không? | Không dùng để kết luận năng suất cá nhân hoặc giá trị sản phẩm |
| Work item age và blocker | Việc nào có nguy cơ kéo dài cần phối hợp? | Cần xem loại việc, phụ thuộc và nguyên nhân |
| Tiến độ đạt Sprint Goal | Sprint đang tạo Increment phục vụ mục tiêu hay không? | Đếm số PBI không thay cho kiểm tra mục tiêu |

Kanban có các phép đo luồng như **WIP, throughput, work item age, cycle time**. Nhóm Scrum có thể sử dụng để tăng minh bạch và inspection, nhưng Scrum **không quy định bắt buộc** phải dùng một bảng Kanban hoặc một bộ số liệu cụ thể.

### 5.4. Câu hỏi tốt hơn “Mọi người đã rõ chưa?”

Trong buổi làm rõ yêu cầu, thay vì hỏi chung chung, hãy kiểm tra bằng ví dụ:

> “Nếu người học vừa bấm ‘Bắt đầu bài đầu’ rồi mạng ngắt, hệ thống phải hiển thị trạng thái gì? Có ghi nhận tiến độ học hay chưa? Chúng ta sẽ kiểm thử cách nào để xác nhận?”

Hội thoại khiến những cách hiểu khác nhau xuất hiện sớm. **Acceptance criteria** có thể ghi thành các kịch bản; kiểm thử và Increment giúp nhóm biết cách hiểu đó đã thành hành vi đúng hay chưa.

### 5.5. Kiểm tra không đồng nghĩa với phán xét một lần

Những gì đúng trong Sprint trước có thể không còn đúng khi lượng người dùng, ràng buộc kỹ thuật hoặc ưu tiên sản phẩm đổi. Một Sprint Review tốt là cuộc thảo luận dựa trên Increment và bối cảnh hiện tại, **không chỉ là buổi trình diễn tính năng đã hoàn thành**.

Tương tự, một Sprint Retrospective có thể kiểm tra vì sao công việc chờ QA quá lâu và tìm điều chỉnh. Nhóm không cần kết luận mọi vấn đề là do người kiểm thử; cần xem WIP, cách chia PBI, thời điểm kiểm thử và sự phối hợp của cả hệ thống.

## 6. Trụ cột thứ ba: Thích ứng (Adaptation)

### 6.1. Thích ứng là gì?

Khi kiểm tra phát hiện tình trạng vượt giới hạn chấp nhận hoặc kết quả không như mong đợi, nhóm cần điều chỉnh **quá trình thực hiện hoặc điều đang được tạo** để giảm sai lệch tiếp theo.

Những điều có thể thích ứng:

- **Product Backlog:** sắp lại thứ tự, làm rõ hoặc bỏ các giải pháp ít giá trị.
- **Sprint Backlog:** Developers điều chỉnh kế hoạch và thương lượng phạm vi với Product Owner khi phát hiện thông tin mới, vẫn bảo vệ Sprint Goal.
- **Thiết kế/giải pháp:** đổi cách triển khai, chia lát cắt nhỏ, bổ sung kiểm thử hoặc spike để giảm rủi ro.
- **Cách phối hợp:** giảm WIP, làm rõ chính sách chuyển giao, trao đổi với đúng người sớm hơn.
- **Chiến lược phát hành/kiểm chứng:** thử với nhóm nhỏ hơn, bổ sung quan sát và phương án khôi phục khi phù hợp.

Thích ứng không phải thay mọi thứ theo ý kiến mới nhất. Mỗi thay đổi nên trả lời được: **“Dữ kiện nào khiến chúng ta đổi? Ta kỳ vọng điều gì tốt hơn? Khi nào kiểm chứng?”**

### 6.2. Ranh giới quan trọng khi thích ứng trong Sprint

Theo Scrum Guide:

- Không thực hiện thay đổi **gây nguy hại Sprint Goal**.
- **Chất lượng không được giảm**.
- Product Backlog có thể được làm rõ và điều chỉnh khi hiểu biết tăng.
- Developers có thể **thương lượng phạm vi với Product Owner** khi học thêm thông tin.
- Nếu Sprint Goal trở nên **lỗi thời**, Product Owner có quyền hủy Sprint.

Vì vậy, việc giảm một tính năng trang trí để tập trung hoàn tất luồng đăng ký đáng tin cậy có thể là thích ứng tốt nếu phù hợp Sprint Goal. Ngược lại, bỏ kiểm thử bắt buộc để tăng số ticket Done không phải thích ứng hợp lý.

### 6.3. Mẫu hành động thích ứng có thể kiểm chứng

~~~text
Quan sát:
  PBI thường dồn sang kiểm thử trong hai ngày cuối Sprint.

Ảnh hưởng:
  Rủi ro không đạt DoD và Sprint Goal tăng; QA bị quá tải.

Giả thuyết:
  Nếu nhóm giảm số PBI bắt đầu cùng lúc và kiểm thử sớm hơn,
  số việc tồn đọng cuối Sprint sẽ giảm.

Thay đổi thử:
  Giữ WIP ở mức nhóm thống nhất cho luồng phát triển;
  cùng hoàn tất story đang mở trước khi kéo thêm việc.

Tín hiệu cần xem:
  Work item age, thời gian chờ QA, PBI đạt DoD,
  lỗi sau triển khai và phản hồi của nhóm.

Điểm đánh giá:
  Trong Sprint Retrospective tiếp theo.

Quyết định tiếp:
  Giữ, điều chỉnh hoặc dừng thử nghiệm theo bằng chứng.
~~~

Mức WIP và thời lượng là **thỏa thuận tùy bối cảnh**, không phải giới hạn chính thức của Scrum. Một thử nghiệm tốt được thiết kế đủ nhỏ để nhóm học sớm mà không làm gián đoạn mục tiêu.

### 6.4. Thích ứng không nhất thiết phải đổi hướng

Nếu kiểm tra cung cấp bằng chứng rằng một lựa chọn vẫn hợp lý, nhóm có thể **giữ nguyên hướng đi** và ghi nhận căn cứ. Quyết định “không đổi” dựa trên quan sát khác với việc không thay đổi vì không ai dám đặt câu hỏi.

## 7. Các sự kiện Scrum tạo cơ hội kiểm tra và thích ứng

Scrum có **Sprint** là sự kiện bao chứa những sự kiện còn lại. Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective tạo nhịp giúp việc kiểm tra và thích ứng diễn ra thường xuyên, có mục tiêu.

| Sự kiện | Điều thường được kiểm tra | Thích ứng có thể xảy ra | Lưu ý |
|---|---|---|---|
| **Sprint Planning** | Product Goal, các PBI đang ưu tiên, năng lực, kết quả mong muốn | Hình thành Sprint Goal, chọn PBI, lập kế hoạch | Không chỉ chọn đủ điểm hay nhận toàn bộ backlog |
| **Daily Scrum** | Tiến độ Developers hướng tới Sprint Goal | Điều chỉnh Sprint Backlog/kế hoạch phối hợp trong ngày | Sự kiện 15 phút cho Developers, không phải họp báo cáo quản lý |
| **Sprint Review** | Increment và những thay đổi của bối cảnh cùng bên liên quan | Thảo luận hướng đi tiếp, điều chỉnh Product Backlog | Không phải một cổng phê duyệt bắt buộc để được phát hành |
| **Sprint Retrospective** | Cách làm, tương tác, công cụ, quy trình và chất lượng | Chọn cải tiến để tăng chất lượng/hiệu quả | Không chỉ liệt kê vấn đề rồi để đó |

### 7.1. Sprint Planning — làm rõ vì sao Sprint có giá trị

Khi bước vào Sprint Planning, Product Owner trao đổi mục tiêu sản phẩm và những PBI quan trọng; Scrum Team hình thành Sprint Goal. Developers chọn công việc trong khả năng hiện tại và lập kế hoạch thực hiện.

Ví dụ, thay vì kế hoạch “hoàn thành 12 ticket đăng ký”, Sprint Goal có thể là:

> “Người học mới có thể đăng ký và mở bài học đầu tiên trong một luồng hoàn chỉnh, có kiểm thử và đo được trạng thái thất bại.”

Mục tiêu này giúp kiểm tra **giá trị Increment**, thay vì chỉ kiểm tra số ticket.

### 7.2. Daily Scrum — kiểm tra tiến độ, không kiểm điểm từng người

Developers kiểm tra tiến độ đối với Sprint Goal và điều chỉnh Sprint Backlog nếu cần. Họ có thể chọn cấu trúc Daily Scrum phù hợp. Mẫu “hôm qua, hôm nay, blocker” **không phải công thức bắt buộc của Scrum Guide**.

Ví dụ trao đổi có ích:

> “Luồng đăng ký chạy ổn, nhưng liên kết mở bài đầu thất bại khi phiên đăng nhập hết hạn. Chúng ta cần hai người cùng tái hiện và sửa trong hôm nay; phần giao diện bổ sung có thể đợi để giữ Sprint Goal.”

Cuộc họp giúp nhóm điều chỉnh hành động. Nếu chỉ có một lượt báo cáo cá nhân mà không ai nhìn Sprint Goal, cơ hội kiểm tra và thích ứng đang bị bỏ lỡ.

### 7.3. Sprint Review — kiểm tra Increment và bối cảnh sản phẩm

Scrum Team cùng các bên liên quan xem điều đã hoàn thành và những gì thay đổi. Đây là **phiên làm việc để điều chỉnh hướng đi**, không chỉ là buổi demo một chiều.

Ví dụ, Increment cho phép người học mở bài đầu trực tiếp; nhưng khi quan sát thử, nhiều người vẫn dừng lại vì nội dung đầu khó hiểu. Product Owner có thể quyết định ưu tiên cải thiện hướng dẫn bài học thay vì bổ sung hiệu ứng giao diện.

**Lưu ý:** Increment có thể được giao cho người dùng trước Sprint Review; Sprint Review **không phải cửa kiểm định phát hành**. Phần chưa đạt DoD không được trình bày như đã hoàn thành.

### 7.4. Sprint Retrospective — thích ứng cách làm

Scrum Team nhìn lại chất lượng và hiệu quả, bao gồm con người, tương tác, quy trình, công cụ và Definition of Done, để xác định cải tiến hữu ích. Nếu nhóm thấy nhiều story bị chặn do chờ quyết định nghiệp vụ, họ có thể thử làm rõ ví dụ sớm hơn.

Không nhất thiết tạo danh sách hàng chục hành động. Một hoặc vài cải tiến rõ **người phụ trách, giả thuyết và cách xem kết quả** thường có giá trị hơn nghi thức ghi nhận nhiều ý tưởng nhưng không ai áp dụng.

### 7.5. Backlog refinement không phải sự kiện Scrum chính thức

**Product Backlog refinement** là hoạt động tiếp tục bổ sung thông tin, chia nhỏ và làm rõ PBI. Nhóm có thể tổ chức các buổi trao đổi khi cần, nhưng Scrum Guide **không quy định đây là một sự kiện chính thức có lịch cố định**.

Trong tinh thần ba trụ cột, refinement hữu ích khi giúp làm rõ nhu cầu, rủi ro và chuẩn chấp nhận để những lựa chọn tiếp theo dựa trên thông tin tốt hơn.

## 8. Scrum Values hỗ trợ ba trụ cột

Scrum Guide nêu năm giá trị: **Commitment (Cam kết), Focus (Tập trung), Openness (Cởi mở), Respect (Tôn trọng) và Courage (Can đảm)**.

| Giá trị | Hành vi hỗ trợ thực nghiệm | Điều trái ngược cần tránh |
|---|---|---|
| **Cam kết** | Chịu trách nhiệm với mục tiêu chung và chất lượng Increment | Coi “cam kết” là hứa không bao giờ thay đổi phạm vi dù dữ liệu mới xuất hiện |
| **Tập trung** | Ưu tiên công việc phục vụ Sprint Goal, giảm việc song song không cần | Nhận thêm yêu cầu tùy hứng làm phân tán nỗ lực |
| **Cởi mở** | Nói rõ rủi ro, trạng thái chưa Done và điều chưa biết | Che lỗi để báo cáo tiến độ đẹp |
| **Tôn trọng** | Lắng nghe bằng chứng từ Developer, Tester, Product Owner và bên liên quan | Quy mọi điểm tắc cho cá nhân và xem ý kiến ngược là chống đối |
| **Can đảm** | Đưa ra vấn đề khó và đề xuất thay đổi có căn cứ | Giữ giải pháp không hiệu quả vì ngại thừa nhận giả định sai |

Các giá trị này không chỉ là khẩu hiệu. Nếu nhóm sợ báo lỗi, **minh bạch sẽ suy giảm**; khi trạng thái thiếu tin cậy, inspection dễ sai; khi không được trao quyền, adaptation khó diễn ra.

### An toàn trong trao đổi

Một thành viên nên có khả năng nói:

> “Tính năng này chưa đạt DoD; nếu coi là Done hôm nay, chúng ta sẽ che rủi ro. Tôi đề xuất giảm phần phụ để kiểm thử xong luồng chính.”

Câu nói như vậy thể hiện trách nhiệm với sản phẩm, không phải thiếu nỗ lực. Nhóm cần phân biệt **trách nhiệm giải trình** với **đổ lỗi**.

## 9. Tình huống xuyên suốt: luồng học đầu tiên không đạt kỳ vọng

### 9.1. Bối cảnh và mục tiêu

Một Scrum Team phát triển nền tảng học trực tuyến, có:

- **Product Goal:** giúp người học mới bắt đầu học và hoàn thành bài đầu thuận lợi.
- **Sprint Goal:** người đăng ký mới có thể mở bài đầu và lưu tiến độ trong một luồng tích hợp đáng tin.
- **PBI chính:** màn chào mừng, mở bài đầu, lưu tiến độ và hiển thị trạng thái khi hệ thống lỗi.

Giữa Sprint, bảng công việc cho thấy nhiều PBI gần hoàn thành. Tuy nhiên, Tester phát hiện:

1. Người học mở bài trên điện thoại rồi chuyển sang máy tính nhưng tiến độ không đồng bộ.
2. Khi mất kết nối, giao diện vẫn báo “Đã lưu” dù chưa có xác nhận từ dịch vụ.
3. Một thành viên đã chuyển story lưu tiến độ sang Done vì code chạy đúng ở môi trường cá nhân.

Những phát hiện này quan trọng vì **trạng thái giả tạo có thể tạo quyết định sai** nếu Sprint Review diễn ra ngay.

### 9.2. Minh bạch: ghi nhận đúng tình trạng

Nhóm cập nhật:

| Thông tin | Trước khi làm rõ | Sau khi làm rõ |
|---|---|---|
| Trạng thái PBI lưu tiến độ | Done | Chưa đạt DoD, đang cần kiểm thử và sửa lỗi |
| Rủi ro | Không thấy trên bảng | Có khả năng báo lưu thành công sai và mất tiến độ |
| Tác động Sprint Goal | “Không ảnh hưởng” | Luồng học đầu chưa đáng tin, có nguy cơ không đạt mục tiêu |
| Phụ thuộc | Không rõ | Cần môi trường tích hợp và dữ liệu thử hai thiết bị |
| Việc cần quyết định | Chưa có | Có hoãn hiệu ứng phụ để tập trung khôi phục luồng chính không? |

Không ai cần tự nhận đã hoàn thành nhiều hay ít hơn. Điều quan trọng là **tất cả cùng nhìn thấy tình trạng hệ thống**.

### 9.3. Kiểm tra: dùng ví dụ và chuẩn chung

Scrum Team làm rõ hành vi mong đợi:

> “Người học chỉ được thấy thông báo đã lưu khi hệ thống có cơ sở xác nhận. Nếu lưu thất bại, giao diện cần phản hồi phù hợp và không làm mất dữ liệu chưa được lưu mà không thông báo.”

Tester, Developer và Product Owner cùng đặt các trường hợp kiểm chứng. Ví dụ Gherkin:

~~~gherkin
Tính năng: Lưu tiến độ học đầu tiên đáng tin cậy

Kịch bản: Lưu tiến độ thành công
  Cho trước người học đã đăng nhập và đang học bài đầu
  Khi hệ thống ghi nhận tiến độ thành công
  Thì người học thấy trạng thái đã lưu phù hợp
  Và tiến độ đã lưu có thể được đọc lại theo quy tắc sản phẩm

Kịch bản: Kết nối mất trước khi xác nhận lưu
  Cho trước người học đang trong phiên học hợp lệ
  Khi dịch vụ lưu tiến độ không xác nhận thành công
  Thì giao diện không thông báo sai rằng tiến độ đã lưu thành công
  Và đưa ra hướng xử lý phù hợp theo chính sách sản phẩm

Kịch bản: Tiến độ được xem từ thiết bị khác
  Cho trước người học đã có tiến độ được xác nhận lưu
  Khi người học đăng nhập từ thiết bị khác được hỗ trợ
  Thì hệ thống hiển thị tiến độ đã lưu theo quy tắc đồng bộ
  Và không tùy tiện ghi đè bằng dữ liệu cũ
~~~

Các tiêu chí này là **minh họa**, chưa phải đặc tả bắt buộc của mọi hệ thống học. Quy tắc đồng bộ, xử lý offline và bảo vệ dữ liệu phải được xác nhận theo sản phẩm thực tế.

Nhóm xem lại Definition of Done để xác định kiểm thử tích hợp, kết quả lưu và xử lý lỗi cần đáp ứng ra sao trước khi coi PBI hoàn thành.

### 9.4. Thích ứng: điều chỉnh để giữ Sprint Goal

Developers thảo luận với Product Owner và chọn:

1. Ưu tiên sửa hành vi lưu sai và kiểm thử tích hợp trên hai thiết bị.
2. Tạm hoãn hiệu ứng minh họa trên màn chào mừng nếu phần đó không thiết yếu cho Sprint Goal.
3. Tạo kịch bản kiểm thử tự động cho trường hợp mất kết nối ở mức phù hợp.
4. Làm việc cùng để kiểm tra luồng đăng ký → mở bài → lưu → mở lại.
5. Chỉ chuyển PBI sang Done khi đáp ứng Definition of Done.

Đây không phải “đổi mục tiêu giữa chừng”. Nhóm **giữ nguyên Sprint Goal** và điều chỉnh cách hoàn thành nó khi phát hiện rủi ro mới.

### 9.5. Sprint Review và dữ liệu sau đó

Tại Sprint Review, Scrum Team trình bày Increment thực sự đạt DoD, nêu rõ phạm vi đã hoàn thành và phản hồi từ người dùng thử. Nhóm có thể quan sát:

| Tín hiệu | Câu hỏi |
|---|---|
| Tỷ lệ mở bài đầu | Người mới có bắt đầu học dễ hơn không? |
| Tỷ lệ lưu tiến độ thành công | Việc lưu có đáng tin trên các bối cảnh được hỗ trợ không? |
| Lỗi lưu và tình huống phải làm lại | Có rủi ro mất công sức học hay không? |
| Tỷ lệ hoàn thành bài đầu | Cải tiến luồng có gắn với Product Goal không? |
| Phản hồi về thao tác trên thiết bị khác | Có nhu cầu sử dụng nào chưa được giải quyết? |

Nếu lượt mở bài tăng nhưng tỷ lệ hoàn thành không cải thiện, **không nên tự khẳng định Product Goal đã đạt**. Nhóm có thể tìm hiểu thêm về độ khó nội dung, khả năng lưu tiến độ hoặc các điểm tắc khác.

### 9.6. Sprint Retrospective: kiểm tra cách làm

Nhóm phát hiện nguyên nhân quá nhiều vấn đề tới cuối Sprint: việc lưu tiến độ được phát triển và kiểm thử tích hợp quá muộn. Một thử nghiệm cải tiến là đưa kiểm thử hành vi quan trọng vào sớm, giới hạn số PBI đang mở và cùng xử lý blocker trước khi nhận việc mới.

Ở Sprint kế tiếp, nhóm quan sát **work item age**, số lỗi tích hợp phát hiện muộn, số PBI chưa đạt DoD gần cuối Sprint và chi phí thời gian kiểm thử. Nếu thay đổi không hữu ích, nhóm tiếp tục điều chỉnh.

### Bài học rút ra

**Minh bạch** làm lộ rủi ro; **kiểm tra** cho thấy rủi ro ảnh hưởng tới mục tiêu và chất lượng; **thích ứng** giúp nhóm đổi phạm vi, giải pháp và cách phối hợp để giao Increment đáng tin. Không nên chỉ ghi nhận một lỗi và gọi đó là đã hoàn thành ba trụ cột.

## 10. Kết hợp Scrum với Kanban và XP mà không đánh đồng khái niệm

Scrum là một **framework** với những vai trò trách nhiệm, artifact, commitment và sự kiện được xác định. Kanban tập trung vào quản lý luồng công việc; Extreme Programming (XP) cung cấp các thực hành kỹ thuật. Chúng có thể bổ trợ cho nhau nhưng không phải là ba tên gọi của cùng một quy trình.

| Nhu cầu | Scrum đóng góp | Kanban hoặc XP có thể hỗ trợ |
|---|---|---|
| Giữ mục tiêu chung rõ | Product Goal, Sprint Goal và Sprint Review | Dùng bảng luồng để xem việc có phục vụ mục tiêu hay bị chặn |
| Biết tình trạng công việc | Product/Sprint Backlog và Increment với DoD | Hiển thị WIP, blocked items, work item age |
| Kiểm tra chất lượng sớm | DoD, kiểm tra Increment | XP: TDD khi phù hợp, kiểm thử tự động, CI, refactoring |
| Thay đổi cách thực hiện an toàn | Scrum Team tự quản lý, điều chỉnh Sprint Backlog | XP: pair programming, kỹ thuật giữ mã dễ đổi |
| Cải tiến hiệu quả luồng | Retrospective và sự kiểm tra liên tục | Kanban: đo cycle time, throughput và điều chỉnh chính sách WIP |

**Lưu ý:** Scrum không yêu cầu một mức WIP cụ thể, không bắt buộc sử dụng story point và không quy định TDD là nghi thức phải có. Nhóm có thể sử dụng nếu giúp tăng hiệu quả của ba trụ cột.

## 11. Phân biệt đầu ra, kết quả và khả năng học hỏi

Một cuộc Sprint Review có thể cho thấy nhóm đã hoàn thành sáu tính năng. Đây là **output**. Điều người dùng cần có thể là một **outcome**, như giảm thời gian đăng ký hoặc tăng khả năng hoàn thành bài đầu. Hai loại thông tin cần được kiểm tra cùng nhau.

| Loại | Ví dụ | Cách dùng |
|---|---|---|
| **Output** | Ba PBI đáp ứng DoD, một Increment mới | Xác nhận nhóm đã giao phần mềm gì, đạt chuẩn ra sao |
| **Outcome** | Tỷ lệ người mới hoàn thành bài đầu tăng | Xem thay đổi có giải quyết nhu cầu người dùng không |
| **Chất lượng** | Lỗi lưu tiến độ, thời gian tải, sự cố sau triển khai | Kiểm tra việc tạo giá trị có đi kèm tác dụng phụ không |
| **Dòng công việc** | Cycle time, WIP, blocker | Điều chỉnh cách làm để giao và học sớm hơn |
| **Giới hạn hiểu biết** | Dữ liệu ít, phân khúc chưa đại diện, thay đổi ngoài kiểm soát | Tránh suy luận chắc chắn về nguyên nhân và quyết định mở rộng |

Không có chỉ số đơn lẻ thay thế được câu hỏi: **“Increment có tạo ra điều gì hữu ích cho người dùng và chúng ta cần học gì tiếp?”**

### 11.1. Ví dụ tính tỷ lệ hoàn thành

Giả sử trong hai đợt quan sát minh họa:

| Giai đoạn | Người mới đủ điều kiện | Hoàn thành bài đầu trong 7 ngày | Tỷ lệ |
|---|---:|---:|---:|
| Trước thay đổi | 200 | 50 | 25% |
| Sau thay đổi | 240 | 72 | 30% |

Tỷ lệ tăng **5 điểm phần trăm**. Nhóm có thể xem đây là tín hiệu tích cực để tiếp tục kiểm tra, **không phải bằng chứng chắc chắn** rằng chỉ riêng thay đổi giao diện đã gây ra sự tăng này. Khác biệt có thể liên quan nguồn người dùng, nội dung bài học, thời điểm đo hoặc những thay đổi cùng lúc.

Khi theo dõi, cần định nghĩa rõ “người mới đủ điều kiện”, “hoàn thành bài” và mốc bảy ngày. Nếu mẫu số hoặc sự kiện đo thay đổi, phải ghi lại trước khi so sánh.

### 11.2. Tránh biến chỉ số thành mục tiêu tự thân

Nếu lãnh đạo yêu cầu “mọi Sprint phải tăng velocity”, nhóm có thể tăng điểm ước lượng hoặc chọn PBI dễ, trong khi Product Goal không tiến triển. Tương tự, tỷ lệ Done cao có thể đánh lừa khi trạng thái thực không phản ánh DoD.

Hãy dùng chỉ số để **đặt câu hỏi và kiểm tra giả thuyết**, không dùng nó như bằng chứng duy nhất để đánh giá cá nhân hay ép Sprint báo cáo đẹp.

## 12. Các sai lầm thường gặp

| Sai lầm | Vì sao gây hại | Cách sửa |
|---|---|---|
| “Có dashboard nghĩa là đã minh bạch.” | Dữ liệu có thể sai, cũ hoặc thiếu chuẩn chung | Xác nhận định nghĩa Done, trạng thái thực và rủi ro |
| “Minh bạch là mọi người phải gửi báo cáo mọi giờ.” | Tốn thời gian và dễ thành giám sát vi mô | Hiển thị thông tin cần thiết cho quyết định, cập nhật khi có thay đổi ý nghĩa |
| “Daily Scrum chỉ để báo cáo cho Scrum Master.” | Developers không kiểm tra và điều chỉnh kế hoạch đạt Sprint Goal | Đưa trọng tâm trở lại tiến độ và phối hợp giữa Developers |
| “Kiểm tra là tìm người làm sai.” | Thành viên có xu hướng giấu lỗi và vấn đề | Kiểm tra sản phẩm, hệ thống làm việc, giả định và điều kiện |
| “Sprint Review là buổi xin duyệt để được release.” | Bỏ lỡ trao đổi về Increment và Product Backlog | Dùng Review để kiểm tra và thích ứng; release có thể diễn ra khi Increment đủ điều kiện |
| “Retrospective càng nhiều ý tưởng càng tốt.” | Không có hành động nào được thực hiện hoặc kiểm chứng | Chọn ít thay đổi có mục đích và xem kết quả ở vòng tiếp |
| “Đã có phản hồi là phải đổi ngay mọi thứ.” | Nhóm mất tập trung, quyết định theo tín hiệu yếu | Làm rõ bằng chứng, tác động lên mục tiêu và đánh đổi |
| “Để kịp Sprint có thể hạ Definition of Done.” | Lỗi bị chuyển sang người dùng, số liệu Done mất đáng tin | Điều chỉnh phạm vi phù hợp và giữ chất lượng |
| “Scrum bắt buộc dùng story point, user story và Kanban board.” | Trộn thực hành tùy chọn với yêu cầu framework | Hiểu rõ những phần Scrum thực sự quy định |
| “Tính năng chạy đúng nên chắc chắn có giá trị.” | Đánh đồng output với outcome | Kiểm tra kết quả sử dụng và tín hiệu bảo vệ |
| “Mọi thay đổi trong Sprint đều vi phạm Scrum.” | Nhóm không dám thích ứng khi có thông tin mới | Bảo vệ Sprint Goal; thương lượng phạm vi khi cần |
| “Chỉ cần họp định kỳ là đã thực nghiệm.” | Có nghi thức nhưng thiếu quan sát và quyết định | Nêu câu hỏi, dùng bằng chứng và khép vòng thích ứng |

## 13. Thực hành thiết kế một vòng lặp Scrum

Một vòng lặp thực nghiệm có thể bắt đầu từ câu hỏi: **“Người học mới có thể mở bài đầu và giữ tiến độ đáng tin cậy không?”**

### 13.1. Chuẩn bị trước Sprint

- Product Owner làm rõ Product Goal và thứ tự PBI theo giá trị, rủi ro.
- Developers nêu phụ thuộc kỹ thuật, cách kiểm thử và khả năng chia nhỏ.
- Scrum Team thống nhất Definition of Done áp dụng; không che những phần chưa đủ để kiểm chứng.
- Bên liên quan cung cấp ví dụ sử dụng hoặc phản hồi phù hợp.

### 13.2. Trong Sprint

- Cập nhật Sprint Backlog khi kế hoạch thực hiện thay đổi.
- Kiểm tra tiến độ đạt Sprint Goal, không chỉ số ticket đã mở.
- Thử luồng tích hợp sớm; nêu rõ blocker và lỗi quan trọng.
- Giữ các phần đã giao đáp ứng DoD.
- Thay đổi cách phối hợp nếu việc đang dở hoặc thời gian chờ tăng bất thường.

### 13.3. Cuối Sprint và sau đó

- Sprint Review kiểm tra Increment và bối cảnh sản phẩm với bên liên quan.
- Product Backlog được điều chỉnh theo điều vừa học.
- Sprint Retrospective xem lại cách phối hợp và chọn cải tiến hữu ích.
- Nhóm quan sát outcome người dùng khi có đủ dữ liệu; không ép phải kết luận mọi giả thuyết ngay cuối Sprint.

### 13.4. Bốn câu hỏi tự kiểm tra nhanh

1. **Minh bạch:** trạng thái PBI, Increment, mục tiêu và rủi ro có đáng tin không?
2. **Kiểm tra:** ai đã đối chiếu chúng với kết quả người dùng và DoD?
3. **Thích ứng:** điều vừa học dẫn đến thay đổi kế hoạch hoặc quyết định nào?
4. **Khép vòng:** khi nào chúng ta kiểm chứng liệu thay đổi đó có tốt hơn không?

## 14. Bài tập vận dụng

### Bài tập 1 — Nhận diện trụ cột còn thiếu

Với mỗi tình huống, chỉ ra trụ cột đang thiếu hoặc yếu và đề xuất một hành động cụ thể:

1. Nhóm ghi 10 PBI Done nhưng 4 PBI chưa qua kiểm thử tích hợp theo DoD.
2. Sprint Review có phản hồi người dùng rằng nút bắt đầu bài rất khó nhìn; không ai cập nhật backlog hoặc quyết định tiếp theo.
3. Nhóm có bảng công việc rõ, số liệu đầy đủ nhưng không bao giờ đối chiếu với Sprint Goal.
4. Nhóm thay đổi ưu tiên mỗi ngày theo người gửi tin nhắn gần nhất mà không nêu bằng chứng hay tác động.
5. Retrospective phát hiện quá nhiều việc bị chặn vì chờ phê duyệt, nhưng Sprint sau vẫn giữ quy trình cũ.

**Gợi ý:** (1) yếu minh bạch; (2) và (5) thiếu thích ứng; (3) thiếu inspection có mục đích; (4) có hành động đổi nhưng thiếu nền tảng minh bạch, kiểm tra và định hướng mục tiêu.

### Bài tập 2 — Đọc bảng Sprint Backlog

Giả sử Sprint Goal là “Người mới có thể đăng ký và mở bài đầu tiên đáng tin cậy”. Trạng thái:

| PBI | Trạng thái được báo | Tình hình thực tế |
|---|---|---|
| Đăng ký tài khoản | Done | Đạt DoD và kiểm thử liên quan |
| Mở bài đầu | Done | Chưa xử lý trường hợp phiên đăng nhập hết hạn |
| Lưu tiến độ | Đang làm | Bị chặn bởi môi trường tích hợp hai ngày |
| Hiệu ứng màn chào mừng | Đang làm | Không trực tiếp cần cho Sprint Goal |

**Yêu cầu:** viết một cập nhật minh bạch cho Daily Scrum; nêu hai câu hỏi kiểm tra và một đề xuất thích ứng nhằm bảo vệ Sprint Goal mà không giảm DoD.

**Gợi ý:** không coi “Mở bài đầu” là Done khi chưa đạt tiêu chuẩn; làm rõ blocker và xem khả năng hoãn hiệu ứng phụ để xử lý luồng chính.

### Bài tập 3 — Từ user story tới inspection

Viết một user story cho tính năng **gửi lại email xác thực**, sau đó viết ba acceptance criteria cho trường hợp thành công, yêu cầu lặp liên tiếp và dịch vụ gửi lỗi.

**Yêu cầu thêm:** chỉ ra điều nào là kiểm tra hành vi kỹ thuật và điều nào cần quan sát sau phát hành để biết trải nghiệm đăng ký đã tốt hơn.

**Gợi ý:** kiểm thử có thể xác minh phản hồi gửi lại và giới hạn chống lạm dụng; outcome có thể là tỷ lệ kích hoạt thành công và mức yêu cầu hỗ trợ.

### Bài tập 4 — Thiết kế một hành động retrospective

Nhóm có nhiều PBI dồn sang QA vào hai ngày cuối Sprint. Hãy điền mẫu:

~~~text
Quan sát minh bạch:
Điều cần kiểm tra (số liệu/ví dụ):
Giả thuyết về nguyên nhân:
Thay đổi nhỏ đề xuất:
Người phối hợp thực hiện:
Tín hiệu chính cần xem:
Tín hiệu bảo vệ về chất lượng:
Thời điểm kiểm tra lại:
Kết quả nào khiến ta giữ/đổi/dừng cách làm:
~~~

**Gợi ý:** có thể thử giới hạn công việc đang làm và kiểm thử sớm hơn; đo work item age, thời gian chờ QA và lỗi, không chỉ số ticket đã đóng.

### Bài tập 5 — Phân biệt artifact và công cụ hỗ trợ

Trong danh sách dưới đây, hãy xác định đâu là **artifact Scrum**, đâu là **commitment** và đâu là **thực hành/công cụ có thể chọn dùng**:

**Product Backlog, Product Goal, Sprint Backlog, Sprint Goal, Increment, Definition of Done, user story, story point, biểu đồ burn-down, bảng Kanban, CI.**

**Đáp án định hướng:**

- Artifacts: **Product Backlog, Sprint Backlog, Increment**.
- Commitments tương ứng: **Product Goal, Sprint Goal, Definition of Done**.
- Các mục còn lại là cách biểu đạt, ước lượng, trực quan hóa hoặc thực hành kỹ thuật có thể hữu ích, nhưng không phải artifact/commitment bắt buộc của Scrum.

### Bài tập 6 — Phân tích dữ liệu sản phẩm

Một luồng mới nâng tỷ lệ hoàn thành bài đầu từ **25% lên 30%** trong hai đợt quan sát khác nhau. Đồng thời, tỷ lệ lỗi ghi tiến độ tăng.

1. Xác định tín hiệu outcome và tín hiệu chất lượng.
2. Giải thích vì sao không thể khẳng định luồng mới là nguyên nhân duy nhất của mức tăng.
3. Đề xuất một quyết định thích ứng cần cân nhắc.
4. Nêu điều kiện hoặc dữ liệu bổ sung cần có trước khi mở rộng cho toàn bộ người dùng.

**Gợi ý:** cải thiện một chỉ số không biện minh cho việc bỏ qua rủi ro mất tiến độ. Cần phân tích nguồn người dùng, lỗi, điều kiện đo và có thể thử trên phạm vi giới hạn.

## 15. Tổng kết

Scrum biến tư duy Agile về phản hồi sớm, giao phần mềm tăng dần và cải tiến liên tục thành **một vòng học hỏi có mục tiêu**:

1. **Minh bạch:** trạng thái thật của công việc, chất lượng, mục tiêu và rủi ro được thể hiện đủ rõ; “Done” phải dựa trên Definition of Done.
2. **Kiểm tra:** thường xuyên so sánh artifact, Increment và kết quả quan sát với Product Goal, Sprint Goal, nhu cầu người dùng và chuẩn chất lượng.
3. **Thích ứng:** điều chỉnh Product Backlog, kế hoạch trong Sprint, giải pháp hoặc cách phối hợp theo bằng chứng, nhưng không làm nguy hại Sprint Goal hay hạ chất lượng.
4. **Các sự kiện Scrum** tạo cơ hội kiểm tra và thích ứng; chúng có giá trị vì mục đích, không phải vì nhóm họp đủ lần.
5. **Artifacts và commitments** cung cấp chuẩn chung để kiểm tra có ý nghĩa; các công cụ như user story, Kanban board hoặc CI có thể bổ trợ khi cần.
6. **Scrum Values** giúp nhóm dám minh bạch vấn đề, kiểm tra trong tinh thần hợp tác và thực hiện cải tiến có trách nhiệm.
7. **Kết quả người dùng** mới là nơi kiểm chứng giá trị, còn số ticket, story point hay cuộc họp chỉ là các tín hiệu hoặc phương tiện hỗ trợ.

> **Câu hỏi ghi nhớ:** “Chúng ta có đang nhìn đúng thực tế, kiểm tra điều quan trọng và thay đổi cách làm dựa trên điều vừa học — hay chỉ đang lặp lại nghi thức Scrum?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — nền tảng empiricism và Lean, ba trụ cột, năm giá trị, sự kiện, artifacts, commitments và trách nhiệm Scrum.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — cộng tác, phản hồi sớm, phần mềm hoạt động được và thích ứng khi nhu cầu thay đổi.
- [The Kanban Guide](https://kanbanguides.org/) — nhìn dòng công việc, WIP, work item age, throughput và cycle time để hỗ trợ kiểm tra.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — kiểm thử, tích hợp liên tục và thực hành kỹ thuật tăng khả năng đổi hướng an toàn.
