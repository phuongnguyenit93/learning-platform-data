# Đồng nhất Agile với tốc độ làm việc cao hoặc thiếu kế hoạch

Một nhóm phát triển nền tảng học trực tuyến được yêu cầu “làm Agile hơn” để ra tính năng **Học tiếp** thật nhanh. Quản lý đặt mục tiêu mỗi Sprint phải hoàn thành nhiều story points hơn Sprint trước, bắt mọi người nhận thêm việc ngay khi rảnh, cắt thời gian refinement để “đỡ họp”, và thông báo rằng vì Agile chấp nhận thay đổi nên không cần thống nhất mục tiêu hay lịch phát hành. Kết quả: Developers chuyển ngữ cảnh liên tục, nhiều user story dở dang, API tiến độ chưa được kiểm tra phân quyền, còn người học vẫn phải tìm thủ công bài đang học.

Một nhóm khác không cố tăng tốc độ gõ mã. Họ làm rõ **vấn đề người học**, chọn một **lát cắt nhỏ có giá trị**, đặt **Sprint Goal** hoặc mục tiêu dòng công việc rõ, kiểm soát lượng việc đang làm, tích hợp và kiểm thử sớm, nhận phản hồi rồi cập nhật kế hoạch. Họ có thể hoàn thành ít ticket hơn nhưng **giao phần mềm đúng nhu cầu và đáng tin sớm hơn**.

Sai lầm chung của cách thứ nhất là **đồng nhất Agile với làm nhanh, luôn bận, ít tài liệu, không dự báo và không lập kế hoạch**. Agile không khuyên tổ chức chạy hết công suất con người, bỏ qua chất lượng hay ngừng suy nghĩ về tương lai. Agile là cách **thích ứng có kỷ luật**: có định hướng, lên kế hoạch phù hợp với điều đã biết, tạo phần mềm hoạt động, kiểm tra thực tế và điều chỉnh khi học được điều mới.

Bài thuộc chương **Sai lầm thường gặp** của module **AGILE_DEVELOPMENT**. Nội dung liên hệ các giá trị và nguyên tắc Agile với user story, backlog, Scrum, Kanban, Extreme Programming (XP), số đo flow và cải tiến liên tục. Mọi con số trong ví dụ là **giả định phục vụ học tập**, không phải tiêu chuẩn áp dụng bắt buộc.

> **Luận điểm trung tâm:** Agile không có nghĩa “càng nhanh càng tốt” hoặc “không cần kế hoạch”. Agile hướng tới **khả năng giao giá trị đáng tin, học từ phản hồi và thay đổi hướng với chi phí/rủi ro chấp nhận được**, nhờ **lập kế hoạch liên tục và nhịp làm việc bền vững**.

## 1. Kết quả học tập

Sau bài học, bạn có thể:

1. Phân biệt **tốc độ bận rộn**, **tốc độ hoàn thành công việc**, **thời gian tới giá trị** và **khả năng thích ứng**.
2. Giải thích vì sao nguyên tắc Agile “phản hồi với thay đổi hơn là làm theo kế hoạch” **không phủ nhận việc lập kế hoạch**.
3. Xác định những loại kế hoạch cần có: **Product Goal, roadmap định hướng, Product Backlog, Sprint Goal/Sprint Backlog, chính sách flow và kế hoạch phát hành**.
4. Hiểu **timebox, feedback cadence, refinement, forecasting** và cách thay đổi phạm vi khi xuất hiện thông tin mới.
5. Nhận diện hệ quả của **quá tải, WIP cao, chuyển ngữ cảnh, thiếu test, nợ kỹ thuật và mục tiêu velocity**.
6. Dùng **cycle time, throughput, work item age, WIP, chất lượng và product outcome** để đánh giá cải thiện thay vì đếm giờ bận/story points.
7. Trình bày **vai trò Scrum, Kanban và XP** trong việc phối hợp giữa kế hoạch thích ứng và chất lượng bền vững.
8. Xử lý tình huống **khách hàng đổi yêu cầu giữa Sprint** mà không tự động coi mọi thay đổi là lệnh phải làm ngay.
9. Phân biệt **forecast xác suất và cam kết mục tiêu**, nhất là khi có bất định, phụ thuộc hoặc sự cố.
10. Đề xuất một cải tiến nhỏ, có giả thuyết và guardrails, khi nhóm đang bị ép “nhanh hơn và ít kế hoạch hơn”.

## 2. Hai ngộ nhận độc lập nhưng thường đi cùng nhau

| Ngộ nhận | Cách hiểu sai | Hành vi dễ phát sinh | Điều Agile thực sự khuyến khích |
| --- | --- | --- | --- |
| **Agile = tốc độ cao** | Mọi người phải code nhiều, đóng ticket nhanh, tăng velocity liên tục | Làm thêm giờ, nhận nhiều việc, bỏ test, đánh giá cá nhân bằng output | **Giao giá trị sớm và thường xuyên**, giữ chất lượng, học nhanh, tối ưu toàn dòng công việc |
| **Agile = không cần kế hoạch** | Vì yêu cầu đổi nên không cần mục tiêu, dự báo, backlog hay chuẩn bị phụ thuộc | Ưu tiên thay đổi mỗi ngày, cam kết mơ hồ, phát hành tùy hứng | **Lập kế hoạch ở mức phù hợp và thường xuyên điều chỉnh** theo thông tin mới |

Hai ngộ nhận có thể khuếch đại nhau: khi không có định hướng ưu tiên, mọi việc đều trở nên “khẩn”; khi mọi người luôn bận, không còn thời gian nghiên cứu, kiểm thử và cập nhật kế hoạch; khi chất lượng giảm, sửa lỗi lại chiếm capacity, khiến quản lý yêu cầu “chạy nhanh hơn”.

### Sơ đồ vòng xoáy quá tải

~~~mermaid
flowchart TD
    A["Áp lực: phải nhanh hơn"] --> B["Nhận nhiều việc cùng lúc<br/>giảm thời gian chuẩn bị"]
    B --> C["WIP và chuyển ngữ cảnh tăng"]
    C --> D["Story già đi, tích hợp và test muộn"]
    D --> E["Rework, lỗi và chậm feedback"]
    E --> F["Giá trị tới người dùng chậm"]
    F --> A
    G["Giới hạn WIP, mục tiêu rõ,<br/>kiểm thử sớm, nhịp bền vững"] -. "Phá vòng xoáy" .-> C
~~~

**Vòng xoáy chỉ là mô hình để tìm hiểu vấn đề**, không phải mọi nhóm chậm đều do WIP. Có thể nguyên nhân là yêu cầu mơ hồ, thiếu môi trường, thay đổi hợp đồng, phụ thuộc pháp lý hoặc kỹ năng cần học. Hãy quan sát dữ liệu trước khi chọn giải pháp.

## 3. Agile Manifesto nói gì về kế hoạch và tốc độ?

Một trong bốn giá trị của Agile Manifesto là **“Responding to change over following a plan”** — ưu tiên **đáp ứng thay đổi** hơn **bám cứng một kế hoạch**. Phần dẫn nhập của Manifesto cũng nhấn mạnh: dù có giá trị ở các yếu tố bên phải, các yếu tố bên trái được coi trọng hơn.

Điều đó có ba hệ quả:

1. **Có kế hoạch là cần thiết.** Không có kế hoạch hoặc mục tiêu, tổ chức không thể biết điều gì đang thay đổi, vì sao đổi và chi phí cơ hội là gì.
2. **Không biến kế hoạch thành chân lý bất biến.** Khi phản hồi thực cho thấy người dùng cần việc khác, nhóm phải có quyền kiểm tra và điều chỉnh.
3. **Thay đổi có điều kiện, không hỗn loạn.** Một thay đổi cần được cân nhắc cùng Product Goal, chất lượng, rủi ro, năng lực, phụ thuộc và những cam kết thực sự.

Các nguyên tắc Agile còn nhấn mạnh **phân phối phần mềm hoạt động thường xuyên**, **duy trì nhịp phát triển bền vững**, **chú trọng kỹ thuật tốt và thiết kế tốt**, **đơn giản hóa** và **định kỳ suy ngẫm để điều chỉnh**. Không có nguyên tắc nào yêu cầu “mỗi Sprint phải có nhiều điểm hơn” hoặc “người làm phải bận 100%”.

### “Giao phần mềm thường xuyên” không bằng “làm vội”

Giao thường xuyên giúp **giảm kích thước thay đổi, rút ngắn vòng feedback và giảm phạm vi rủi ro mỗi lần**. Để làm được, nhóm thường cần nhiều kỷ luật hơn: story slicing, kiểm thử tự động theo rủi ro, tích hợp sớm, quản lý release và Definition of Done rõ. Cắt bỏ các bước cần thiết có thể khiến một bản demo xuất hiện nhanh nhưng **giá trị được kiểm chứng xuất hiện chậm hơn**.

## 4. Phân biệt “nhanh” theo bốn câu hỏi

Khi lãnh đạo hoặc khách hàng yêu cầu “nhanh hơn”, nhóm nên hỏi **nhanh ở bước nào và để đạt điều gì**.

| Khía cạnh | Câu hỏi đúng | Dữ liệu khả dĩ | Điều chưa chứng minh |
| --- | --- | --- | --- |
| **Activity speed** | Một người thực hiện thao tác/code nhanh đến đâu? | Thời gian thao tác, số commit nếu phù hợp điều tra kỹ thuật | Giá trị, chất lượng, hiệu suất toàn nhóm |
| **Flow speed** | Một work item đi từ start tới finish trong bao lâu? | Cycle time, work item age, blocked time | Tính năng giải quyết đúng nhu cầu |
| **Delivery speed** | Thay đổi đã được kiểm chứng tới môi trường sử dụng an toàn nhanh thế nào? | Lead time thay đổi kỹ thuật, CI feedback, thời gian triển khai | Feature đã được mở cho người dùng hoặc họ được lợi |
| **Value feedback speed** | Mất bao lâu từ giả thuyết tới bằng chứng người dùng? | Time-to-feedback, task success, phản hồi, cohort | Impact lâu dài được chứng minh chắc chắn |

### Ví dụ đối lập

Nhóm A viết xong frontend cho Học tiếp trong **hai ngày**, nhưng phải đợi API, security review và staging thêm **12 ngày**. Nhóm B mất **ba ngày** tạo lát cắt đầu tiên tích hợp, đạt kiểm tra quyền và có thể cho người học thử. Không thể kết luận A “nhanh hơn” chỉ vì phần code họ sở hữu được viết sớm hơn; cần xem **ranh giới công việc và kết quả đầu cuối**.

### Thời gian không phải tất cả

Một bản sửa nhanh gây lộ checkpoint là **không chấp nhận được**, ngay cả khi lead time giảm. Một tính năng được phát hành sớm nhưng không giúp học viên tìm lại bài vẫn thiếu **product outcome**. Khả năng thích ứng cần **thời gian, chất lượng, khả năng học và giá trị** đi cùng nhau.

## 5. Agile vẫn có nhiều tầng kế hoạch

Một tổ chức Agile thường có **kế hoạch ở các khoảng thời gian và độ chi tiết khác nhau**. Kế hoạch càng xa càng cần linh hoạt với bất định, trong khi phần việc đang triển khai phải đủ rõ để kiểm tra chất lượng.

| Tầng kế hoạch | Câu hỏi | Ví dụ sản phẩm học tập | Cách thích ứng |
| --- | --- | --- | --- |
| **Định hướng sản phẩm / Product Goal** | Trạng thái giá trị tương lai là gì? | Người học quay lại hành trình học đúng và tin cậy | Điều chỉnh khi bằng chứng chiến lược thay đổi |
| **Roadmap định hướng** | Những vấn đề/cơ hội nào đáng khám phá trước? | Tìm lại bài, lưu tiến độ, hỗ trợ đa thiết bị | Cập nhật khi giả thuyết, chi phí hoặc phụ thuộc thay đổi |
| **Product Backlog** | Những việc gì được sắp thứ tự để cải thiện sản phẩm? | Story Học tiếp, test quyền, quan sát tác vụ | Refinement và sắp thứ tự liên tục |
| **Sprint Goal / kế hoạch Sprint nếu dùng Scrum** | Mục tiêu chung hiện tại và cách đạt là gì? | Người còn quyền mở đúng bài dở từ trang khóa học | Developers điều chỉnh Sprint Backlog khi học thêm; bảo vệ Sprint Goal |
| **Workflow/flow policy nếu dùng Kanban** | Khi nào pull, ưu tiên blocker, xử lý WIP? | Không kéo story mới nếu Review đầy | Kiểm tra và sửa chính sách bằng dữ liệu |
| **Release/rollout plan** | Khi nào có thể đưa bản an toàn tới người dùng và theo dõi? | Phát hành thử Học tiếp, theo dõi checkpoint | Điều chỉnh exposure, dừng khi guardrail bị vi phạm |

Một team không cần dùng **tất cả kỹ thuật và biểu mẫu** trong bảng. Quan trọng là có **định hướng, quyền quyết định, kế hoạch ngắn đủ cụ thể và cơ chế cập nhật**.

### Kế hoạch không nhất thiết là lịch cố định của mọi tính năng

Một roadmap có thể mô tả **vấn đề cần giải quyết, mức độ tin cậy và khoảng thời gian dự kiến**, không nhất thiết chốt chính xác ngày cho mọi feature khi giải pháp chưa được khám phá. Nếu có hạn thực từ hợp đồng hoặc quy định, nhóm vẫn phải **lập kế hoạch phụ thuộc và quản lý rủi ro đúng hạn**; Agile không xóa nghĩa vụ thực.

## 6. Lập kế hoạch thích ứng là một vòng lặp, không phải một cuộc họp

~~~mermaid
flowchart LR
    A["Mục tiêu và vấn đề<br/>người dùng"] --> B["Dự báo và chọn<br/>lát cắt ưu tiên"]
    B --> C["Lập kế hoạch ngắn<br/>với chất lượng rõ"]
    C --> D["Xây, tích hợp,<br/>kiểm tra sớm"]
    D --> E["Quan sát Increment<br/>và phản hồi"]
    E --> F{"Giả định còn đúng?"}
    F -->|Có| G["Tiếp tục / mở rộng<br/>an toàn"]
    F -->|Không hoặc chưa rõ| H["Sửa giả thuyết,<br/>đổi backlog/kế hoạch"]
    G --> E
    H --> A
~~~

Lập kế hoạch Agile có thể diễn ra khi **Product Backlog được refinement**, trong Sprint Planning, mỗi lần Developers điều chỉnh kế hoạch ở Daily Scrum, trong Sprint Review khi sản phẩm được kiểm tra, hoặc lúc team Kanban chọn việc theo chính sách pull. Không phải chỉ lập kế hoạch một lần rồi “để nhóm tự chạy”.

### Bao nhiêu kế hoạch là đủ?

Không có một tỷ lệ phần trăm thời gian lập kế hoạch đúng cho mọi nhóm. Mức chuẩn bị phải cân với:

- **Độ bất định sản phẩm:** chưa hiểu nhu cầu thì cần khám phá/thử nghiệm sớm.
- **Rủi ro kỹ thuật:** migration dữ liệu, phân quyền và môi trường production đòi kiểm tra sâu hơn.
- **Phụ thuộc xuyên nhóm:** cần hợp đồng và thời điểm trao đổi đủ sớm.
- **Thời hạn bên ngoài:** hạn học kỳ, hợp đồng hoặc luật có thể yêu cầu dự báo rõ.
- **Tốc độ phản hồi:** nếu có thể thử giải pháp nhỏ sau vài ngày, không cần cố thiết kế mọi chi tiết cho sáu tháng.

Mục tiêu không phải **giảm tối đa thời gian họp**, mà là **chi phí lập kế hoạch tương xứng giá trị và rủi ro**, đủ để người tham gia ra quyết định tốt và điều chỉnh khi cần.

## 7. Tại sao bỏ kế hoạch thường làm chậm hơn?

Không có hướng ưu tiên, nhóm có thể nhận việc vì **người yêu cầu gần nhất hoặc nói lớn nhất**, trong khi những công việc dở bị bỏ lại. Khi không làm rõ tiêu chí chấp nhận, nhóm viết sai quy tắc. Khi bỏ kế hoạch tích hợp, producer/consumer phát hiện API không tương thích ở cuối kỳ. Mỗi lần như vậy đều **tạo việc sửa lại và chờ thêm**.

| Việc bị bỏ qua | Hậu quả có thể xảy ra | Kế hoạch tối thiểu hữu ích |
| --- | --- | --- |
| **Product Goal/ưu tiên** | Mọi yêu cầu đều “gấp”, không biết nói không với việc ít giá trị | Thống nhất vấn đề, trade-off và ai sắp Product Backlog |
| **User story/acceptance examples** | Chức năng đúng theo suy nghĩ lập trình viên nhưng sai nghiệp vụ | Làm rõ một vài ví dụ quan trọng trước khi code |
| **Dependency planning** | UI xong nhưng API/schema chưa sẵn | Xác định owner, contract và điều kiện tích hợp sớm |
| **Quality planning** | Lỗi dữ liệu và quyền chỉ thấy sau release | Nêu rủi ro, test strategy, Definition of Done |
| **Release/rollback considerations** | Có code nhưng không thể đưa cho người dùng an toàn | Plan exposure, monitoring, khôi phục khi cần |
| **Feedback plan** | Phát hành xong không biết có giúp ai | Định nghĩa outcome, nguồn dữ liệu và thời gian đánh giá |

**Không có kế hoạch** có thể tạo ảo giác bắt đầu làm sớm, nhưng **thời gian đến khi phần mềm có ích và an toàn** lại kéo dài.

## 8. “Đáp ứng thay đổi” không đồng nghĩa nhận mọi yêu cầu ngay

Phản hồi mới có thể quan trọng. Nhưng nếu mỗi ý tưởng hoặc email được lập tức kéo vào Doing, toàn bộ hệ thống sẽ bị gián đoạn, Sprint Goal mất ý nghĩa và thời gian hoàn tất khó dự báo.

### Phân loại thay đổi trước khi quyết định

| Loại thay đổi | Ví dụ | Phản ứng phù hợp |
| --- | --- | --- |
| **Sự cố nghiêm trọng** | Lộ quyền học hoặc mất checkpoint production | Xử lý ngay theo incident/severity policy, bảo vệ dữ liệu |
| **Thông tin mới làm mục tiêu hiện tại kém phù hợp** | Người dùng không cần dashboard rộng mà cần Học tiếp rõ ràng | Product Owner/nhóm xem lại ưu tiên, mục tiêu và phương án |
| **Làm rõ phạm vi trong cùng mục tiêu** | Chọn bài dở gần nhất hay bài người học chọn? | Làm rõ ví dụ, Developers điều chỉnh kế hoạch thực hiện |
| **Ý tưởng mới nhưng không khẩn** | Thêm huy hiệu mới khi đang làm luồng tiến độ | Đưa vào Product Backlog, đánh giá giá trị và thứ tự |
| **Thay đổi kỹ thuật phát sinh** | API contract không tương thích | Phối hợp giải quyết và điều chỉnh dự báo, giữ chất lượng |
| **Deadline thực** | Quy định truy cập mới có hiệu lực vào một ngày đã biết | Lập kế hoạch ngược từ điều kiện bắt buộc, quản lý rủi ro |

### Câu hỏi trước khi nhận việc mới

1. Nó **giải quyết vấn đề người dùng nào**, có bằng chứng gì?
2. Có phải **sự cố hoặc nghĩa vụ bắt buộc** không?
3. Nó có hỗ trợ **Product Goal/Sprint Goal** hay làm thay đổi chúng?
4. Nếu bắt đầu ngay, **việc nào sẽ chậm hoặc bị dừng**, ai chấp nhận trade-off?
5. Có đủ năng lực và cách bảo vệ **Definition of Done/guardrails**?
6. Có thể **thử một lát cắt nhỏ hơn** để học trước khi đầu tư lớn?

**Linh hoạt không phải không có giới hạn.** Sự linh hoạt có giá trị khi tổ chức biết **điều cần giữ vững** (mục tiêu, chất lượng, nghĩa vụ) và **điều có thể điều chỉnh** (phạm vi giải pháp, thứ tự, kế hoạch làm việc).

## 9. Scrum: có mục tiêu, có kế hoạch, có điều chỉnh hằng ngày

Scrum là một framework nhẹ để tạo giá trị qua những giải pháp thích ứng cho vấn đề phức tạp. **Scrum không đồng nghĩa “làm gì cũng được trong Sprint” hoặc “phải tăng story points qua mỗi Sprint”.**

### Các artifact và commitment liên quan

| Artifact | Commitment | Vai trò trong lập kế hoạch |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Định hướng trạng thái tương lai của sản phẩm; backlog được sắp thứ tự và tinh chỉnh khi học thêm |
| **Sprint Backlog** | **Sprint Goal** | Thể hiện mục tiêu Sprint, những Product Backlog Items đã chọn và kế hoạch thực hiện, cập nhật khi công việc tiến triển |
| **Increment** | **Definition of Done** | Bảo đảm phần công việc được tính là Increment đạt các tiêu chuẩn chất lượng đã xác định |

Ba commitment trên không phải “bộ KPI tăng tốc”. Chúng tạo **định hướng, tính minh bạch và chất lượng** để Scrum Team kiểm tra/thích ứng mà không làm mất mục tiêu chung.

### Sprint Planning không chỉ là chia ticket

Sprint Planning trả lời các nội dung trọng yếu:

1. **Tại sao Sprint này có giá trị?** Product Owner đề xuất cách sản phẩm có thể gia tăng giá trị và Scrum Team cùng xây Sprint Goal.
2. **Có thể hoàn tất những gì trong Sprint?** Developers chọn Product Backlog Items phù hợp dựa trên kinh nghiệm và khả năng hiện tại, với trao đổi cùng Product Owner.
3. **Công việc được thực hiện như thế nào?** Developers lập kế hoạch để các PBI đã chọn chuyển thành Increment đáp ứng Definition of Done.

Đây là một **kế hoạch thực tế có thể điều chỉnh**, không phải hợp đồng bắt mỗi người hoàn tất một số điểm cố định bất chấp phát hiện mới.

### Daily Scrum không phải báo cáo giờ làm

Daily Scrum giúp Developers **kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog**. Nếu thấy hai story chờ review, họ có thể thay cách phối hợp, pairing hoặc ưu tiên hoàn tất, chứ không cần mỗi người đọc một danh sách công việc cho quản lý.

### Sprint Review không phải trình diễn số ticket

Sprint Review dùng để kiểm tra **kết quả Sprint, tình trạng sản phẩm và môi trường**, trao đổi với bên liên quan, từ đó quyết định điều chỉnh tiếp Product Backlog. Có thể sản phẩm được kiểm chứng và phát hành **trước Sprint Review** nếu Increment đạt chất lượng và policy phát hành cho phép; không cần đợi cuối Sprint mới có phản hồi.

### Sprint Retrospective không phải “cố làm nhanh hơn”

Scrum Team kiểm tra điều gì giúp/cản trở **chất lượng và hiệu quả**, rồi chọn cải tiến thiết thực. Ví dụ thay thỏa thuận review hoặc tăng tự động hóa test khi thấy tích hợp bị chặn. Cải tiến nên được đánh giá theo **flow, chất lượng, giá trị và tính bền vững**, không phải chỉ tốc độ cá nhân.

## 10. Khi yêu cầu đổi giữa Sprint: bảo vệ Sprint Goal, không cố định từng task

Một câu hiểu sai phổ biến là “Agile chấp nhận thay đổi, nên khách hàng có thể thêm một story vào bất kỳ lúc nào và team phải làm ngay”. Trong Scrum, Sprint Goal tạo **tính nhất quán và linh hoạt**; phạm vi công việc cần thiết có thể được làm rõ hoặc thương lượng lại khi học thêm, **miễn không gây nguy hiểm cho Sprint Goal và không giảm chất lượng**.

### Tình huống thực hành

Sprint Goal là **“Học viên đủ quyền có thể mở lại đúng bài đang dở”**. Giữa Sprint, đội phát hiện:

- **Vấn đề A:** Nếu học viên có hai thiết bị, checkpoint có thể xung đột, ảnh hưởng mục tiêu và tính đúng dữ liệu.
- **Yêu cầu B:** Marketing muốn thêm bảng thành tích học viên vì chiến dịch tháng sau.
- **Sự cố C:** API trả checkpoint của tài khoản khác trong một trường hợp lỗi.

| Việc mới | Phản ứng hợp lý | Tại sao |
| --- | --- | --- |
| **A — dữ liệu xung đột** | Developers và Product Owner làm rõ quy tắc; điều chỉnh Sprint Backlog và phạm vi để giữ Sprint Goal/DoD | Là học hỏi trực tiếp về cách đạt mục tiêu an toàn |
| **B — bảng thành tích** | Product Owner đưa vào/điều chỉnh thứ tự Product Backlog; cân nhắc Sprint sau hoặc một trade-off được làm rõ | Không tự động chen vào mục tiêu hiện tại |
| **C — lộ dữ liệu** | Xử lý khẩn theo incident/security policy; đánh giá lại kế hoạch, capacity và ảnh hưởng | An toàn người dùng là guardrail không thể bỏ qua |

### Ai quyết định điều gì trong Scrum?

Product Owner chịu trách nhiệm **tối đa hóa giá trị và quản lý hiệu quả Product Backlog**. Developers chịu trách nhiệm **tạo Increment đạt Definition of Done** và điều chỉnh kế hoạch thực hiện. Scrum Master hỗ trợ Scrum Team và tổ chức **thực hiện Scrum hiệu quả**. Nhóm có thể thương lượng phạm vi với Product Owner trong Sprint khi cần.

Nếu Sprint Goal trở nên **lỗi thời (obsolete)**, **Product Owner có thẩm quyền hủy Sprint** theo Scrum Guide. Điều đó khác việc một quản lý hoặc bên liên quan bất kỳ được tự ý thay Sprint Goal mỗi ngày. Không nên dùng “có thể hủy Sprint” như thủ thuật quản trị thường xuyên để ép thêm việc.

### Một đoạn hội thoại hợp lý

> **Bên liên quan:** “Thêm bảng thành tích vào Sprint này được không? Agile mà.”  
> **Product Owner:** “Đây có thể là ý tưởng tốt. Sprint hiện tập trung vào việc học viên mở lại bài an toàn. Tôi sẽ xem giá trị và độ khẩn của bảng thành tích, đồng thời công khai việc nào phải thay nếu ưu tiên thay đổi. Nếu đây không phải sự cố hoặc nghĩa vụ khẩn, chúng ta đưa vào Product Backlog để sắp thứ tự. Nhóm sẽ giữ Sprint Goal và chất lượng.”

Đó là **thích ứng có trách nhiệm**, không phải sự cứng nhắc hay chống khách hàng.

## 11. Velocity không đo giá trị và không phải thước đo năng suất con người

**Velocity** thường là số story points (hoặc đơn vị ước lượng tương đương) của những work items được hoàn tất theo cách một team tự định nghĩa trong một Sprint. Đây là một **công cụ lập kế hoạch/dự báo nội bộ tùy chọn**, không phải metric bắt buộc của Scrum Guide, cũng không phải đơn vị năng suất có thể so giữa các đội.

### Bốn hiểu nhầm cần tránh

| Hiểu nhầm | Vì sao sai | Cách dùng tốt hơn |
| --- | --- | --- |
| “Team A velocity 60 tốt hơn team B velocity 30” | Thang ước lượng, loại việc và Definition of Done khác nhau | So lịch sử cùng team để hỗ trợ forecast khi phù hợp |
| “Mỗi Sprint velocity phải tăng 10%” | Năng lực hữu hạn; công việc và mức bất định thay đổi | Theo dõi tính ổn định/dự báo, flow, quality và outcome |
| “Ai có nhiều story points là làm tốt hơn” | Points ước lượng **work item**, không phản ánh đóng góp cá nhân; khuyến khích tranh điểm | Đánh giá chất lượng hợp tác và giá trị trong bối cảnh, không xếp hạng points |
| “Hoàn tất điểm là đạt Sprint Goal” | Các PBIs có thể Done nhưng không tạo mục tiêu chung, hoặc Sprint Goal đạt với phạm vi điều chỉnh | Kiểm tra Sprint Goal, Increment/DoD và kết quả sản phẩm |

### Vì sao mục tiêu tăng velocity dẫn tới số liệu đẹp giả?

Giả sử team hoàn tất **10 stories × 3 points = 30 points** trong một Sprint. Khi quản lý yêu cầu 45 points, nhóm có thể:

- Ước lượng lại cùng loại việc từ 3 thành 5 points.
- Chia một story thành nhiều task có tổng points lớn hơn.
- Chỉ nhận việc dễ, trì hoãn lỗi khó hoặc nợ kỹ thuật.
- Gọi Done khi code merged mà chưa tích hợp/kiểm thử.
- Làm thêm giờ để đổi lấy số đẹp trong ngắn hạn.

Trong mọi trường hợp, **velocity có thể tăng mà năng lực tạo giá trị không tăng**, thậm chí chất lượng và niềm tin giảm. Cố biến số đo thành target thưởng/phạt thường làm **mất giá trị dự báo ban đầu của nó**.

### Khi nào velocity vẫn hữu ích?

Trong một team ổn định, có thang ước lượng và Definition of Done tương đối nhất quán, lịch sử points Done có thể giúp đặt **kỳ vọng về lượng công việc phù hợp với capacity**. Nó chỉ là **một nguồn thông tin** cùng với mức bất định, phụ thuộc, nghỉ phép và tính chất công việc. Không được coi nó là cam kết rằng Sprint tiếp theo phải bằng hoặc cao hơn Sprint trước.

## 12. “Luôn bận” khác “hoàn thành giá trị”: tác hại của WIP cao

**Work in Progress (WIP)** là công việc đã bắt đầu nhưng chưa đạt điểm kết thúc theo workflow. Nếu mỗi người phải luôn có nhiều việc đang gán, hệ thống có thể tối ưu **utilization cá nhân** nhưng kéo dài thời gian từng item đi đến Done.

### Ví dụ minh họa hai cách tổ chức

| Cách làm | Dấu hiệu | Rủi ro hoặc kết quả cần xem |
| --- | --- | --- |
| **A — ai rảnh cũng kéo việc mới** | 12 stories Doing, Review/Verify đầy, 3 blockers chưa gỡ | Nhiều việc dở, chuyển ngữ cảnh, review chờ, story già |
| **B — ưu tiên hoàn tất** | 4–6 stories đang dở, Developers hỗ trợ review/test khi cần | Ít việc song song, feedback sớm; vẫn cần kiểm tra throughput và quality |

Không thể kết luận B tốt trong mọi trường hợp chỉ từ WIP thấp. **WIP limit quá chặt hoặc phân bổ kỹ năng không phù hợp cũng có thể tạo chờ**. Giải pháp là chọn chính sách theo workflow, thử và đo.

### Hình dung dòng công việc

~~~text
Cách A — bắt đầu nhiều, hoàn tất ít

Ready      Doing               Review/Test        Done
  ▢       ▣ ▣ ▣ ▣ ▣ ▣           ▣ ▣ ▣ ▣             ✓
          ▣ ▣ ▣

Cách B — bắt đầu vừa đủ, giúp hoàn tất

Ready      Doing               Review/Test        Done
  ▢ ▢ ▢    ▣ ▣                   ▣ ▣                 ✓ ✓ ✓
~~~

Hình chỉ minh họa cấu trúc, không phải dữ liệu thực. Điều quan trọng là **nhìn cả flow của công việc đã bắt đầu** và chủ động xử lý blocked items; không che blocker bằng cách chuyển sang danh sách ngoài quy trình.

### Little's Law: quan hệ flow, không phải công thức tăng năng suất cá nhân

Với hệ thống ổn định đủ điều kiện, đơn vị nhất quán và ranh giới flow rõ:

\[
\text{Average WIP}\approx\text{Average Throughput Rate}\times\text{Average Cycle Time}.
\]

Ví dụ hệ thống có throughput trung bình **2 items/ngày** và WIP trung bình **10 items**, thời gian lưu trong hệ thống trung bình tương ứng khoảng **5 ngày**, nếu các điều kiện của quan hệ trên thỏa mãn. Đây là **quan hệ mô tả trung bình**, không có nghĩa cứ giảm WIP một nửa là bảo đảm mọi story xong nhanh gấp đôi. Tính không ổn định, thay đổi đơn vị work item, WIP ngoài ranh giới và biến động demand có thể làm diễn giải sai.

### Chính sách ưu tiên hoàn tất

Một thỏa thuận có thể thử là: “Khi Review/Verify đạt WIP limit, Developers xem việc nào gần Done hoặc đang bị chặn để hỗ trợ trước khi pull thêm feature.” Nhóm theo dõi **work item age, cycle time, throughput, lỗi lọt và làm thêm giờ** để biết thay đổi có ích hay không.

## 13. Nhịp làm việc bền vững không phải một phần thưởng sau deadline

Agile Manifesto nêu **Agile processes promote sustainable development**, với khả năng duy trì một nhịp độ ổn định lâu dài. Điều này không phải lời khuyên “chỉ làm khi thấy thoải mái”; nó là nhận định thực tế: **làm thêm giờ liên tục, mất tập trung và bỏ bảo trì kỹ thuật thường khiến lỗi và rework tích lũy**, làm hệ thống kém thích ứng.

### Khi nào phải nghi ngờ yêu cầu “nhanh hơn”?

- Team liên tục cam kết vượt capacity rồi dùng cuối tuần để bù.
- Mỗi Sprint có thêm việc khẩn nhưng mục tiêu và forecast không được cập nhật.
- Người làm không dám báo estimate cao hoặc blocker vì sợ bị đánh giá.
- Quality checks bị hoãn với lời hứa “sửa sau khi release”.
- Chuyên gia review/SRE nhận yêu cầu từ nhiều team, luôn on-call không có thời gian phục hồi.
- Số ticket Done tăng nhưng **lỗi production, nghỉ việc, sự cố dữ liệu hoặc support load** tăng theo.

### Capacity planning có tính đến thực tế

Một Sprint hai tuần có **10 ngày làm việc danh nghĩa** không có nghĩa một Developer có **10 ngày lập trình không gián đoạn**. Cần tính đến trao đổi nghiệp vụ, review, kiểm thử, hỗ trợ production, nghỉ phép và học kỹ năng. Không có tỷ lệ “chỉ được plan 70% capacity” đúng cho mọi team; hãy dựa vào **lịch sử tương đồng và nhu cầu thực tế**.

### Guardrails về con người

Cải tiến nên theo dõi **làm thêm giờ không mong muốn, chuyển ngữ cảnh, mức hỗ trợ chéo, an toàn khi nêu trở ngại và khả năng phục hồi sau incident**. Thu dữ liệu cần tôn trọng quyền riêng tư; không dùng bảng theo dõi giờ phút của từng người để tự động kết luận họ “ít Agile”.

### Khi phải chạy gấp vì sự cố thật

Một incident mất dữ liệu nghiêm trọng có thể đòi huy động khẩn cấp. **Sustainable pace không có nghĩa bỏ mặc sự cố**. Nó yêu cầu tổ chức có **severity policy, on-call hợp lý, năng lực dự phòng, khôi phục và hậu kiểm**, rồi điều chỉnh kế hoạch thường lệ thay vì coi gián đoạn khẩn là năng suất miễn phí.

## 14. Kanban: có kế hoạch và giới hạn thông qua chính sách flow

Kanban không bắt buộc dùng Sprint hoặc lập kế hoạch cho một danh sách cố định mỗi hai tuần. Tuy nhiên, nó **không đồng nghĩa không cần ưu tiên, capacity, tiêu chí Done hay dự báo**. Kanban dựa vào **Definition of Workflow (DoW)** để làm rõ ranh giới công việc, trạng thái, chính sách và cách kiểm soát WIP.

### Các thành phần cần được hiểu rõ

| Thành phần | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Loại work item** | Công việc nào được quản lý cùng workflow? | Feature nhỏ, lỗi thường lệ; incident có thể có đường riêng |
| **Start/finish** | Khi nào item bắt đầu và được coi hoàn tất? | Bắt đầu Doing; Done khi đáp ứng tiêu chí phù hợp |
| **WIP control** | Có thể làm cùng lúc bao nhiêu, điều gì xảy ra khi đầy? | Khi Review đạt giới hạn, ưu tiên hỗ trợ hoàn tất |
| **Explicit policies** | Pull, blocked, expedited và quality được xử lý thế nào? | Work item không đủ rõ không được pull; incident theo policy |
| **Flow metrics** | WIP, throughput, work item age, cycle time cho biết gì? | Xem tuổi item, độ biến thiên và xu hướng |
| **Service Level Expectation (SLE)** | Với xác suất nào, work item kỳ vọng hoàn tất trong bao lâu? | Ví dụ 85% feature nhỏ trong tối đa 10 ngày làm việc |

### SLE không phải “deadline tuyệt đối”

SLE ví dụ **85% trong 10 ngày** mang ý nghĩa xác suất và phạm vi định nghĩa; không bảo đảm 100% items sẽ Done ngày thứ mười. Một item hiện đã 9 ngày cần được xem xét **blocked reasons và nguy cơ**, không phải tự động gán người làm kém vì “sắp trễ”.

### Không ép Kanban thành “không biết việc gì sắp tới”

Một nhóm Kanban vẫn cần **replenishment/prioritization** để chọn việc phù hợp với mục tiêu và năng lực, biết những việc đã được cam kết theo chính sách và dự báo dựa trên data. Khác biệt là **cách quản lý flow và nhịp pull**, không phải việc thiếu kế hoạch.

## 15. XP: tốc độ thay đổi đến từ chất lượng và feedback kỹ thuật

Extreme Programming (XP) liên hệ trực tiếp với hiểu nhầm “muốn nhanh thì cắt test”. XP khuyến khích thực hành như **TDD/test-first, continuous integration, refactoring, pair programming, simple design và small releases**, giúp thay đổi nhỏ và nhận phản hồi sớm hơn.

| Cách làm vội | Hệ quả | Thực hành XP có thể hỗ trợ |
| --- | --- | --- |
| Viết feature lớn rồi mới tích hợp | Contract/API breaks xuất hiện muộn | CI và tích hợp thường xuyên |
| Không kiểm tra quy tắc checkpoint | Lỗi dữ liệu xuất hiện sau release | TDD/unit/API tests theo rủi ro |
| Không refactor vì “không tạo feature” | Code khó sửa, thay đổi sau ngày càng chậm | Refactoring có bảo vệ của tests |
| Một người hiểu mọi phần khó | Review và sửa lỗi chờ chuyên gia | Pairing/knowledge sharing |
| Chỉ release khi tất cả việc lớn hoàn thành | Feedback người dùng chậm | Small releases/vertical slices có giá trị |
| UI báo thành công trước khi API xác nhận | Người dùng tin nhầm trạng thái lưu | Ví dụ nghiệp vụ, tests và trạng thái rõ |

### Ví dụ kiểm thử một điều kiện chất lượng

~~~gherkin
Feature: Học tiếp đúng quyền và trạng thái tiến độ

  Scenario: Học viên mở lại đúng bài đang dở
    Given học viên A còn quyền vào khóa K
      And checkpoint của A chỉ tới bài B
    When A chọn Học tiếp
    Then hệ thống mở đúng bài B
      And không tiết lộ tiến độ của người khác

  Scenario: Chỉ hiển thị lưu thành công khi có xác nhận
    Given học viên A đang học bài B
    When yêu cầu lưu checkpoint bị hệ thống từ chối
    Then giao diện không hiển thị trạng thái Đã lưu thành công
      And người dùng được thông báo phù hợp về thất bại
~~~

Các kịch bản minh họa phải được **xác nhận với quy tắc nghiệp vụ thực tế**. Tests tự động không tự chứng minh mọi yêu cầu an toàn; vẫn cần kiểm thử khám phá, review kiến trúc và đánh giá rủi ro khi phù hợp.

### Technical excellence là điều kiện để linh hoạt

Khi code thiếu regression tests và môi trường không đáng tin, mỗi thay đổi nhỏ có thể gây hậu quả lớn, khiến tổ chức càng phải giữ kế hoạch cứng để tránh rủi ro. Đầu tư kỹ thuật nhằm **giảm chi phí thay đổi có kiểm soát**, không phải “công việc phụ” chỉ được làm khi hết backlog.

## 16. User story và backlog: ưu tiên giá trị, không chạy theo số lượng

Một hiểu lầm nữa là “làm nhanh” bằng cách **xé mọi user story thành thật nhiều task**. Chia việc có thể hỗ trợ lập kế hoạch, nhưng nếu những phần được hoàn tất **không tạo ra hành trình dùng được**, chỉ số output sẽ đánh lừa.

### Ví dụ tách Học tiếp

**Cách tách theo lớp kỹ thuật:**

1. Xây nút trên giao diện.
2. Xây API lấy checkpoint.
3. Xây bảng database.
4. Viết integration test sau cùng.

Mỗi phần có thể đóng ticket riêng, nhưng **chưa có lát cắt người học sử dụng được** cho tới khi tất cả các phần được tích hợp đúng.

**Cách tách theo giá trị và rủi ro:**

1. Người học đủ quyền, có một checkpoint hợp lệ có thể mở đúng bài đang dở.
2. Người chưa có checkpoint nhận hành vi bắt đầu khóa hợp lệ.
3. Khi checkpoint lỗi/hết quyền, không mở sai bài hoặc lộ dữ liệu.
4. Có nhiều thiết bị hoặc checkpoint: xử lý xung đột theo quy tắc đã xác nhận.
5. Tinh chỉnh UI sau khi quan sát người dùng cần điều gì.

Các lát cắt trên có thể được **xác minh và phản hồi từng bước** theo điều kiện chất lượng. Chúng không bắt buộc phải được phát hành ra toàn bộ người dùng ngay khi Done nếu có rủi ro cần rollout có kiểm soát.

### Refinement không phải lãng phí

Product Backlog refinement là hoạt động **liên tục chia nhỏ, bổ sung chi tiết và làm rõ** các item khi cần; nó không mặc định phải là một cuộc họp cố định dài mỗi tuần. Một ít trao đổi đúng lúc về **user story, acceptance examples, phụ thuộc và rủi ro** có thể tiết kiệm nhiều ngày rework.

### Ưu tiên có trade-off

Khi một stakeholder muốn thêm feature mới, Product Owner có thể hỏi **giá trị, bằng chứng, chi phí cơ hội và mức độ khẩn**, sau đó điều chỉnh thứ tự Product Backlog. “Agile” không có nghĩa tất cả ý tưởng đều được triển khai ngay; **nói không hoặc chưa làm** đôi khi là điều kiện để tạo giá trị tốt hơn.

## 17. Forecast không phải lời hứa chắc chắn, càng không phải “khỏi cần dự báo”

Khi phần mềm còn bất định, rất khó biết chính xác ngày hoàn tất. Nhưng khách hàng, nhóm vận hành và tổ chức vẫn cần **dự báo để phối hợp**. Agile khuyến khích làm rõ **điều đã biết, điều giả định, xác suất và những lựa chọn khi kết quả thay đổi**, chứ không ngừng dự báo.

### Ba khái niệm nên tách riêng

| Khái niệm | Nội dung | Ví dụ |
| --- | --- | --- |
| **Target** | Kết quả hoặc mốc mong muốn | Muốn có bản Học tiếp đủ chuẩn để kiểm chứng trong tháng |
| **Forecast** | Dự đoán dựa trên bằng chứng và giả định | Có khả năng giao 6–9 PBIs cùng loại trong hai Sprint, với điều kiện phụ thuộc không đổi |
| **Commitment** | Điều được cam kết theo vai trò hoặc hợp đồng | Sprint Goal và Definition of Done theo Scrum; cam kết bên ngoài nếu có phải được quản lý rõ |

**Một forecast không nên được tự động biến thành nghĩa vụ cá nhân tuyệt đối.** Nhưng “đây chỉ là forecast” cũng không miễn trách nhiệm giải thích khi rủi ro thay đổi, cập nhật dự báo và phối hợp với bên chịu ảnh hưởng.

### Ví dụ dự báo dựa trên throughput

Giả sử một workflow có throughput lịch sử của **sáu tuần cùng loại công việc**:

~~~text
Tuần:        1  2  3  4  5  6
Items Done:  3  5  4  4  6  2
~~~

Tổng cộng 24 items trong sáu tuần, trung bình **4 items/tuần**. Nếu backlog còn 12 items **tương tự về ranh giới và tính chất**, phép chia thô là:

\[
\frac{12\ \text{items}}{4\ \text{items/tuần}}=3\ \text{tuần}.
\]

**Ba tuần không phải bảo đảm**. Lịch sử có biến thiên 2–6 items/tuần; nhu cầu mới, nghỉ phép, incident, blockers hoặc thay đổi kích thước items có thể làm dự báo thay đổi. Với quyết định quan trọng, có thể dùng **dữ liệu lịch sử và mô phỏng Monte Carlo/forecast phân vị** thích hợp, công bố các khoảng/xác suất cùng giả định; không chỉ chia bình quân rồi tuyên bố deadline chắc chắn.

### Các phương án khi có deadline thực

Nếu lịch khai giảng yêu cầu phát hành trước một mốc không thể dời, tổ chức có thể:

1. **Giữ chất lượng và điều kiện bắt buộc**.
2. Sắp thứ tự **mức giá trị và rủi ro**, tách lát cắt tối thiểu có ích.
3. Dùng dữ liệu để dự báo **phạm vi có thể hoàn tất**, thay vì hứa mọi feature.
4. Xác định phụ thuộc và phương án dự phòng.
5. Báo sớm khi kết quả thực khác giả định, đàm phán phạm vi hoặc mốc trong quyền hạn phù hợp.

**Agile không xóa deadline**; nó giúp làm rõ **điều có thể linh hoạt** để đáp ứng deadline mà không hy sinh chất lượng hoặc che giấu rủi ro.

## 18. Dùng metrics để cải thiện hệ thống, không để bắt người “chạy nhanh”

Một bộ số đo tốt giúp trả lời **tổ chức đang giao giá trị và học nhanh hơn mà vẫn an toàn không**. Các số đo về flow, kỹ thuật và sản phẩm có vai trò khác nhau.

| Nhóm số đo | Ví dụ | Hỗ trợ quyết định | Không nên dùng để |
| --- | --- | --- | --- |
| **Flow** | WIP, throughput, work item age, cycle time | Điều chỉnh pull, tìm hàng đợi và rủi ro chậm | Xếp hạng năng suất từng người |
| **Delivery/reliability** | Thời gian thay đổi tới production, deployment frequency, thất bại thay đổi, khả năng phục hồi | Đầu tư CI/CD, rollout và cải tiến độ tin cậy | Kết luận feature có giá trị từ số deploy |
| **Quality** | Lỗi checkpoint, API authorization tests, lỗi lọt production, flaky CI | Chọn kiểm thử và kiểm soát rủi ro | Lấy test count hoặc coverage làm bằng chứng chất lượng tuyệt đối |
| **Product outcome** | Task success, time-to-resume, meaningful return, phản hồi học viên | Chọn giải pháp và điều chỉnh Product Backlog | Tự suy nhân quả từ một con số before/after |
| **Sustainability** | Làm thêm giờ, gián đoạn, blocked reasons, khả năng hỗ trợ chéo | Điều chỉnh capacity, chính sách và phối hợp | Giám sát chi tiết hoạt động cá nhân hoặc trừng phạt người báo lỗi |

### Ba lỗi đo lường hay đi cùng áp lực tốc độ

**Lỗi 1 — đổi đơn vị:** Team đổi cách chia story từ 3 thành 10 task, throughput tăng nhưng số lát cắt dùng được không tăng.

**Lỗi 2 — đổi mốc Done:** Trước kia Done sau integration checks, nay Done khi PR merged, khiến cycle time “giảm” nhưng phần việc còn chưa đủ chuẩn.

**Lỗi 3 — giấu khó khăn:** Khi số blocked days thành KPI xếp hạng, người làm ngừng ghi blocked, khiến báo cáo ngày càng xanh trong khi công việc vẫn chờ.

Để tránh các lỗi trên, cần **định nghĩa vận hành, nguồn dữ liệu, ranh giới đo, cửa sổ và cách xử lý công việc ngoại lệ**.

### Mẫu hợp đồng metric ngắn

~~~text
METRIC: cycle_time_feature_to_done
PURPOSE: thời gian đưa một feature PBI tới DoD theo workflow.
POPULATION: feature PBIs cùng loại, không gộp incidents nếu khác flow.
START: lúc PBI bắt đầu làm theo chính sách đã ghi.
FINISH: lúc đạt Definition of Done áp dụng.
UNIT: ngày làm việc; công bố nếu dùng ngày lịch.
WINDOW: các item hoàn tất trong bốn tuần quan sát.
AGGREGATION: median, phân bố, số lượng item và các ca ngoại lệ.
SEGMENTS: phụ thuộc API, loại rủi ro, mobile/backend nếu phù hợp.
GUARDRAILS: errors, rework, security incidents, overtime.
OWNER: người/nhóm chịu trách nhiệm định nghĩa và độ tin cậy dữ liệu.
~~~

**Nếu metric không đáng tin, hãy sửa cách đo trước khi ép team đạt target.**

## 19. Kết quả người dùng là thước đo cuối gần nhất của việc “nhanh hơn”

Một nhóm có thể rút ngắn thời gian deploy từ ba ngày xuống 10 phút, nhưng nếu người học vẫn không tìm được bài đang học, **chúng ta mới cải thiện khả năng giao kỹ thuật**, chưa xác nhận giá trị sản phẩm.

### Chuỗi kết quả của tính năng Học tiếp

| Cấp độ | Ví dụ | Câu hỏi tiếp theo |
| --- | --- | --- |
| **Output** | Nút Học tiếp và API checkpoint được đưa vào Increment đạt DoD | Người dùng có cơ hội sử dụng chưa? |
| **Exposure** | Tính năng bật cho một nhóm học viên đủ điều kiện | Có được nhìn thấy và hiểu đúng? |
| **Outcome tác vụ** | Người dùng mở đúng bài trong khoảng thời gian có ý nghĩa | Thực sự giảm ma sát so với cách cũ? |
| **Outcome học tập** | Người dùng hoàn thành hoạt động học có ích sau khi mở bài | Trải nghiệm tiếp tục có tạo giá trị? |
| **Impact** | Người học đạt mục tiêu học tập, kiến thức bền vững hơn | Có đủ bằng chứng dài hạn và loại trừ yếu tố khác? |

**Tối ưu cho lượt bấm nút** có thể làm tăng click mà người học vẫn mở sai bài. **Tối ưu thời gian dùng app** có thể giữ người học lâu hơn vì UI rườm rà. Outcome cần gắn với **công việc người dùng muốn hoàn thành**, có guardrails về dữ liệu và trải nghiệm.

### Ví dụ tính task success

Một thử nghiệm quan sát **180 tác vụ hợp lệ** từ người học còn quyền và có bài dở; có **126 tác vụ mở đúng bài trong 60 giây**:

\[
\text{Task success rate}=\frac{126}{180}\times100\%=70\%.
\]

**70% tác vụ không mặc định là 70% học viên.** Một học viên có thể lặp lại nhiều lần; cần phân biệt người, phiên và lượt. Cũng không thể khẳng định nút mới gây ra toàn bộ thay đổi nếu có chiến dịch nhắc học, thay cấu trúc khóa hoặc thay cách tracking cùng thời điểm.

### Khi metric kỹ thuật tốt nhưng outcome chưa tốt

Nhóm không nên bỏ CI vì “không giúp người dùng”, cũng không nên tiếp tục xây các feature lớn vì “chúng ta deploy rất nhanh”. **Năng lực giao hàng tốt** giúp thử các giả thuyết sản phẩm khác với chi phí thấp hơn. Hai dòng học hỏi **kỹ thuật** và **giá trị người dùng** bổ trợ nhau nhưng không thay thế nhau.

## 20. Timebox là giới hạn thời gian để tập trung và học, không phải lệnh cắt chất lượng

Timebox là một khoảng thời gian tối đa/được xác định nhằm tạo **nhịp phối hợp và feedback**. Trong Scrum, Sprint có độ dài cố định **một tháng hoặc ngắn hơn**; một số sự kiện cũng có timebox. Nhóm có thể dùng timebox cho spike nghiên cứu hoặc phiên làm rõ yêu cầu.

| Timebox | Giá trị khi dùng đúng | Hiểu sai dễ gây hại |
| --- | --- | --- |
| **Sprint** | Nhịp ngắn để kiểm tra tiến triển tới Product Goal qua Increment/feedback | “Đến cuối Sprint mọi task phải đóng bằng mọi giá” |
| **Sprint Planning** | Chọn mục tiêu và kế hoạch phù hợp với năng lực | “Chỉ là buổi chia ticket để ai cũng có đủ điểm” |
| **Daily Scrum** | Điều chỉnh kế hoạch để tiến tới Sprint Goal | “Mỗi người đọc báo cáo cho quản lý” |
| **Spike có timebox** | Giảm bất định kỹ thuật/sản phẩm với kết quả học hỏi rõ | “Sau hai ngày nhất định phải code xong sản phẩm” |
| **Workshop/refinement ngắn** | Làm rõ một rủi ro hoặc ví dụ nghiệp vụ | “Kết thúc timebox thì tự động coi mọi vấn đề đã rõ” |

### Đúng nghĩa “timebox một spike”

Ví dụ một spike trong hai ngày hỏi: **“Có thể lưu checkpoint an toàn khi hai tab cùng cập nhật mà không ghi đè sai không?”**. Kết quả mong muốn có thể là một **prototype, những giả định đã loại trừ, trade-off và rủi ro còn lại**, không phải feature production hoàn chỉnh.

Nếu đến cuối timebox vẫn chưa có câu trả lời, nhóm cần **quyết định dựa trên bằng chứng**: thử tiếp, chọn giải pháp đơn giản hơn hoặc thay hướng. Không nên hứa một kết quả kỹ thuật chưa được chứng minh chỉ để “đạt timebox”.

### Chất lượng không phải phạm vi thương lượng tùy tiện

Khi hạn đến gần, có thể điều chỉnh **phạm vi, ưu tiên và độ phức tạp giải pháp** trong quyền hạn phù hợp. Không được tùy tiện bỏ qua các kiểm tra bắt buộc khiến Increment không đạt Definition of Done hoặc vi phạm nghĩa vụ an toàn.

## 21. Phụ thuộc nhiều nhóm và kế hoạch tích hợp: nhanh từng đội có thể chậm cả hệ thống

Một sai lầm phổ biến là đo nhóm frontend, backend, QA và platform riêng rẽ rồi yêu cầu **mỗi nhóm tăng tốc**, trong khi giá trị chỉ xuất hiện khi các phần **tích hợp được**.

### Ví dụ hành trình “Học tiếp”

~~~mermaid
flowchart LR
    A["User story:<br/>mở lại đúng bài"] --> B["UI và hành vi người dùng"]
    A --> C["API checkpoint<br/>và phân quyền"]
    A --> D["Dữ liệu/contract"]
    B --> E["Tích hợp sớm + tests"]
    C --> E
    D --> E
    E --> F["Increment đạt DoD"]
    F --> G["Rollout an toàn"]
    G --> H["Feedback người học"]
~~~

Nếu UI xong trong hai ngày nhưng API contract chờ bảy ngày, thì **thêm hai Developers vào UI** có thể không rút ngắn thời gian tới Increment. Cải tiến cần hướng tới **rào cản chính**: làm rõ contract sớm, self-service staging, chia vertical slice, review đúng rủi ro và quan sát end-to-end waiting time.

### Kế hoạch phụ thuộc tối thiểu

| Phụ thuộc | Thông tin cần rõ trước khi làm sâu | Bằng chứng khi hoàn tất |
| --- | --- | --- |
| **API** | Producer/consumer, schema, quyền, lỗi, version | Contract/API tests và tích hợp hành vi chính |
| **Dữ liệu** | Quy tắc checkpoint, migration/compatibility, quyền sở hữu | Tests, migration check và giám sát dữ liệu |
| **Platform** | Môi trường, pipeline, secrets và support path | Có thể deploy artifact đã kiểm tra theo policy |
| **Người dùng** | Outcome và cách xác minh, đối tượng đủ điều kiện | Task success/feedback trên nhóm phù hợp |
| **Vận hành** | Owner, monitoring, rollback/roll-forward khi cần | Guardrails và quy trình xử lý incident rõ |

**Agile không phải viết kế hoạch tích hợp dài hàng trăm trang cho mọi thay đổi.** Nhưng phụ thuộc quan trọng cần được phát hiện và kiểm chứng **trước khi chúng thành bất ngờ cuối Sprint**.

## 22. Thiết kế một cuộc trao đổi cân bằng tốc độ, phạm vi, rủi ro và giá trị

Khi lãnh đạo nói “cần giao nhanh hơn”, tránh đáp ngay bằng “chúng tôi sẽ tăng 30% velocity”. Cũng không nên phản ứng “Agile thì không cam kết gì được”. Cần chuyển cuộc trao đổi sang **lựa chọn có trade-off minh bạch**.

### Mẫu trao đổi trong nhóm sản phẩm

> **Bên liên quan:** “Chúng ta phải ra toàn bộ trang tiến độ trước tuần khai giảng.”  
> **Product Owner:** “Mục tiêu người học quan trọng nhất là quay lại đúng bài. Nếu hạn không đổi, tôi đề xuất lát cắt Học tiếp trước; dashboard phân tích rộng có thể được kiểm chứng và bổ sung sau. Nhóm sẽ đưa ra forecast dựa trên công việc đã hiểu, giải thích phụ thuộc và giữ các kiểm tra bảo mật. Chúng ta cần quyết định rõ phần nào ưu tiên, phần nào không làm trong đợt đầu.”  
> **Developers:** “Chúng tôi có thể kiểm chứng trường hợp một checkpoint hợp lệ trước, nhưng phải có API contract và test quyền. Chúng tôi sẽ cập nhật kế hoạch khi học thêm về đồng bộ đa thiết bị.”  
> **Bên liên quan:** “Vậy cho tôi mốc đánh giá rủi ro và một bản dùng thử đủ chuẩn để xem.”

### Bốn lựa chọn thường có thể thương lượng

| Biến số | Có thể điều chỉnh như thế nào? | Điều không nên làm |
| --- | --- | --- |
| **Phạm vi** | Lát cắt nhỏ, chọn kết quả thiết yếu trước, bỏ tính năng ít giá trị | Gọi một nửa giao diện chưa chạy là feature Done |
| **Thời gian** | Thay mốc khi không bị ràng buộc; hoặc công bố khoảng dự báo | Hứa ngày chắc chắn khi chưa hiểu rủi ro |
| **Năng lực** | Gỡ blocker, hỗ trợ kỹ năng, đầu tư CI, điều chỉnh ưu tiên | Chỉ thêm người vào điểm nghẽn không giải quyết phụ thuộc |
| **Rủi ro/chất lượng** | Giảm scope, dùng rollout nhỏ, kiểm chứng bằng tests | Bỏ kiểm soát bắt buộc hoặc lộ dữ liệu để “nhanh” |

**Không phải mọi biến số đều có thể đánh đổi.** Yêu cầu bảo mật nghiêm trọng hoặc hợp đồng có thể tạo ràng buộc không thương lượng; khi đó cần **điều chỉnh các biến số còn lại** và báo sớm hệ quả.

## 23. Case study: hai Sprint, hai cách hiểu “phải Agile hơn”

Tình huống dưới đây là **mô phỏng học tập**. Các số liệu được chọn để cho thấy sự khác biệt giữa bận rộn, có kế hoạch và có bằng chứng; chúng không phải dữ liệu một dự án có thật hoặc kết luận nhân quả đã được kiểm chứng.

### 23.1. Vấn đề sản phẩm

Người học của nền tảng thường không tìm được bài đang học dở. Nhóm sản phẩm muốn cung cấp một tính năng **Học tiếp** để học viên đủ quyền mở lại đúng bài với ít thao tác, đồng thời giữ nguyên tính đúng của checkpoint và phân quyền.

**Product Goal liên quan:** Người học có thể duy trì hành trình học thuận tiện và tin cậy.

**Giả thuyết giá trị:** Nếu có một đường Học tiếp rõ ràng, người học đủ điều kiện sẽ mở lại đúng bài nhanh hơn. Điều cần đo là **task success, thời gian tác vụ, lỗi checkpoint và phản hồi**, không chỉ số lượt click.

### 23.2. Cách A — “làm nhanh, đừng lập kế hoạch”

Quản lý áp target tăng story points 25%. Team không làm rõ API contract, không chọn Sprint Goal, nhận toàn bộ các yêu cầu về trang tiến độ. Developers nhận việc theo chuyên môn riêng, dự kiến đến cuối Sprint mới tích hợp; tests dự định “làm nếu còn thời gian”.

Trong hai tuần:

- Ngày 1–3: UI, API và database cùng bắt đầu nhưng thiếu ví dụ thống nhất về checkpoint.
- Ngày 4–6: stakeholder bổ sung thống kê thời gian học và huy hiệu; mọi nhóm nói “đang làm” mà không công khai việc nào phải trì hoãn.
- Ngày 7–8: tích hợp phát hiện API trả checkpoint sai quyền trong một trường hợp.
- Ngày 9: mọi người ở lại muộn để sửa lỗi, một vài story được đánh dấu “code complete”.
- Ngày 10: demo dùng dữ liệu giả, Increment chưa đạt quality criteria và chưa thể cho học viên thử an toàn.

Số ticket Doing rất cao; số story points ước lượng cũng có thể cao. Nhưng **Sprint Goal không rõ, sản phẩm không có lát cắt có thể dùng an toàn và phản hồi người dùng vẫn chưa tới**.

### 23.3. Cách B — mục tiêu rõ, lập kế hoạch vừa đủ, feedback sớm

Team dành thời gian ngắn kiểm chứng vấn đề và thống nhất ví dụ nghiệp vụ:

- Người học còn quyền và có checkpoint hợp lệ mở lại đúng bài.
- Người không có checkpoint được hướng dẫn bắt đầu hợp lệ.
- Người không còn quyền không được đọc checkpoint hoặc nội dung không được phép.
- Trạng thái “Đã lưu” chỉ xuất hiện khi backend xác nhận theo quy tắc.

**Sprint Goal:** “Học viên còn quyền có thể mở lại bài đang dở từ trang khóa học trong một lát cắt tích hợp và an toàn.”

Product Owner cùng Developers chọn PBIs phù hợp; Developers lập kế hoạch test/API và các phụ thuộc, không hứa toàn bộ dashboard rộng.

### 23.4. Kế hoạch làm việc minh họa trong một Sprint hai tuần

| Thời điểm | Kết quả mong muốn | Kiểm tra và phản hồi |
| --- | --- | --- |
| **Đầu Sprint** | Sprint Goal, một lát cắt giá trị, contract và quyền được làm rõ | Acceptance examples, rủi ro, capacity và DoD |
| **Những ngày đầu** | API checkpoint và UI đi cùng một lát cắt nhỏ | Unit/API/authorization checks, CI và pairing khi cần |
| **Giữa Sprint** | Luồng hợp lệ chạy được trên môi trường thử | Demo hành vi thật, quan sát lỗi và điều chỉnh Sprint Backlog |
| **Những ngày kế** | Xử lý trường hợp thất bại quan trọng và kiểm tra end-to-end | Regression tests, exploratory checks, xem blocked age |
| **Cuối hoặc sớm hơn nếu sẵn sàng** | Increment đạt DoD, kế hoạch exposure an toàn | Feedback người học và Sprint Review để cập nhật hướng |

Đây **không phải lịch bắt buộc** phải hoàn tất mỗi bước vào đúng ngày. Nếu phát hiện vấn đề phân quyền ngày 2, phải xử lý theo rủi ro ngay; nếu Increment đạt DoD ngày 7, không cần giữ lại đến ngày 10 chỉ vì lịch demo.

### 23.5. Kết quả giả định của hai cách tiếp cận

| Dấu hiệu | Cách A | Cách B | Ý nghĩa cần xem |
| --- | --- | --- | --- |
| Công việc được bắt đầu | 14 work items | 6 work items | Bắt đầu nhiều không đồng nghĩa hoàn tất nhiều |
| Lát cắt tích hợp đạt DoD | 0 | 2 lát cắt liên quan mục tiêu | B có bằng chứng về phần mềm dùng được, với điều kiện DoD thật |
| Thời gian chờ API clarification | 5 ngày | 1 ngày | Có tín hiệu làm rõ sớm giảm chờ |
| Lỗi phân quyền quan trọng trước rollout | Phát hiện muộn | Phát hiện qua tests sớm | Thời điểm phát hiện quan trọng; lỗi chưa thấy không có nghĩa không tồn tại |
| Giờ làm thêm cuối Sprint | Nhiều | Ít hơn theo ghi nhận | Cần đối chiếu tải và sự cố, không chỉ cảm nhận |
| Feedback người học | Chưa thể thu an toàn | Có thể thu trên lát cắt thử phù hợp | B biết thêm về giá trị, chưa chứng minh tác động dài hạn |

**Không được suy từ bảng giả định rằng cách B luôn tốt với mọi tình huống.** Điều quan trọng là cách B đã **làm rõ mục tiêu, bảo vệ chất lượng, kiểm chứng theo lát cắt và cập nhật kế hoạch khi có thông tin**, thay vì cố tăng lượng việc đang bận.

### 23.6. Một bất ngờ thật trong cách B

Giữa Sprint, quan sát cho thấy nút Học tiếp **khó thấy trên điện thoại**. Câu hỏi Product Owner cần đặt không phải “làm sao đóng thêm hai story UI trước thứ Sáu?”, mà là “giả thuyết trải nghiệm nào cần sửa, việc gì sẽ tạo ra bằng chứng nhanh và phần nào của Sprint Goal còn phù hợp?”.

Developers có thể đề xuất một điều chỉnh nhỏ về nhãn/vị trí nếu **không gây nguy hiểm cho Sprint Goal và chất lượng**, hoặc đưa kiểm chứng sâu hơn vào Product Backlog. Thay đổi dựa trên phản hồi **không phải phá kế hoạch**, mà là **điều chỉnh một kế hoạch có mục tiêu để đạt giá trị tốt hơn**.

### 23.7. Bài học từ case study

**Cách A** tối ưu tốc độ bắt đầu và số lượng hoạt động. **Cách B** tối ưu **thời gian đến một Increment đúng, có thể kiểm chứng và có phản hồi**, bằng cách làm kế hoạch đủ rõ và giữ tính thích ứng.

Một kế hoạch Agile có thể thay đổi nhiều lần. Giá trị của nó nằm ở chỗ **giúp nhận ra lệch hướng sớm**, chứ không phải giấy tờ phải bảo vệ bất chấp thực tế.

## 24. Khi nhóm đang quá tải: khung khôi phục trong hai tuần

Giả sử team hiện có nhiều work items ở Doing, không có mục tiêu rõ, có lỗi production và lãnh đạo yêu cầu tăng velocity. Không nên ngay lập tức triển khai một “Agile transformation” đầy đủ nghi thức. Có thể bắt đầu bằng một **thí nghiệm cải tiến ngắn và an toàn**.

### Bước 1 — Làm rõ hậu quả trước mắt

Xác định **sự cố an toàn, dữ liệu hoặc chất lượng** cần xử lý ngay; bảo vệ người dùng trước khi xem tốc độ. Ghi những việc đang dở và phụ thuộc thật, không xóa item để giảm WIP báo cáo.

### Bước 2 — Thống nhất một mục tiêu giá trị

Ví dụ: “Trong khoảng làm việc này, ưu tiên đưa luồng mở đúng bài đạt DoD để có thể kiểm chứng với người học.” Product Owner làm rõ thứ tự backlog, Developers trao đổi về năng lực và rủi ro.

### Bước 3 — Giảm số việc khởi động thêm

Thử một **pull policy**: khi hàng chờ review/test đã đầy, nhóm hỗ trợ hoàn tất trước khi kéo thêm story mới. Điều chỉnh WIP limit dựa trên năng lực và loại việc, không sao chép con số cố định.

### Bước 4 — Đưa phản hồi kỹ thuật tới sớm

Chọn một vài **quy tắc nghiệp vụ rủi ro cao** và thêm kiểm tra phù hợp vào CI/API; làm rõ trường hợp sai quyền và xung đột checkpoint. Không đặt mục tiêu tăng số lượng tests không gắn rủi ro.

### Bước 5 — Chia việc theo lát cắt

Đổi các tasks rời thành một số **lát cắt dùng được và kiểm chứng end-to-end**. Xác nhận điều kiện Done và thời điểm có thể nhận feedback.

### Bước 6 — Theo dõi bằng chứng mỗi ngày

Xem **work item age, blocked reasons, CI health và chất lượng**; nếu có incident, phản ứng ngay. Có thể dùng Daily Scrum hoặc flow review ngắn tùy cách làm thực tế, không biến thành họp báo cáo cho quản lý.

### Bước 7 — Đánh giá sau một cửa sổ đủ thông tin

So kết quả với baseline có cùng định nghĩa: **WIP, median/đuôi cycle time, throughput, lỗi, làm thêm giờ và giá trị người dùng**. Ghi giải thích thay thế; một Sprint có quá ít items không đủ để kết luận chắc chắn.

### Bước 8 — Quyết định, không chỉ họp

Giữ, sửa hoặc dừng những chính sách có bằng chứng; cập nhật workflow, automated checks, backlog hoặc ownership. Đừng kết thúc bằng câu “mọi người sẽ cố gắng nhanh hơn”.

### Mẫu thẻ thử nghiệm

~~~text
PROBLEM:
  12 stories đang dở, 4 stories chờ review >3 ngày, lỗi tích hợp muộn.

HYPOTHESIS:
  Ưu tiên hoàn tất và test API sớm sẽ giảm thời gian chờ,
  giúp story đạt DoD nhanh hơn mà không giảm chất lượng.

CHANGE:
  Khi Review/Verify đầy, hỗ trợ review/test trước khi kéo việc mới;
  thêm checks checkpoint/quyền vào CI.

SCOPE:
  Feature PBIs liên quan tiến độ trong hai tuần thử.

EVIDENCE:
  WIP, work item age, cycle time, review wait,
  CI reliability, defects, feedback và tải nhóm.

GUARDRAILS:
  Không tăng sai quyền/mất dữ liệu, không yêu cầu tăng ca kéo dài.

DECISION:
  Giữ/sửa/dừng sau review; xử lý rủi ro nghiêm trọng ngay.
~~~

**Một thử nghiệm không biến mọi số liệu thành bằng chứng nhân quả.** Nó giúp nhóm có **thỏa thuận cụ thể, dữ liệu và vòng học**, thay cho các khẩu hiệu khó kiểm chứng.

## 25. Trách nhiệm lãnh đạo: đừng yêu cầu Agile nhưng giữ cơ chế ép tốc độ cũ

Một tổ chức không thể kỳ vọng nhóm tự chủ và giao giá trị an toàn nếu người quản lý vẫn thay ưu tiên tùy ý, cấp capacity theo mức bận tuyệt đối và thưởng cho việc đóng nhiều ticket.

### Các thay đổi ở cấp hệ thống cần xem xét

| Cơ chế quản lý | Tác dụng phụ | Điều chỉnh có trách nhiệm |
| --- | --- | --- |
| **Cam kết cố định cả thời gian, scope và nguồn lực bất chấp bất định** | Team giấu rủi ro, bỏ chất lượng hoặc tăng giờ làm | Công khai trade-off, forecast và quyền chỉnh phạm vi |
| **KPI tăng velocity hàng Sprint** | Chia vụn/ước lượng lại points, chỉ nhận việc dễ | Dùng metric theo giá trị và flow, không xếp hạng người |
| **Bắt mọi người bận 100%** | Không có capacity review, hỗ trợ blocker hay học hỏi | Giảm WIP, cân bằng tải theo dòng giá trị |
| **Thêm việc mới qua nhiều kênh** | Sprint Goal mất trọng tâm và WIP tăng | Quy tắc Product Backlog/triage và đường incident riêng |
| **Cắt test/refinement vì “không tạo feature”** | Lỗi và rework dồn cuối kỳ | Giữ DoD, bảo vệ time-to-feedback và làm rõ rủi ro |
| **Phê duyệt tay mọi thay đổi nhỏ** | Queue dài và phụ thuộc chuyên gia | Chính sách theo rủi ro, self-service và kiểm soát tự động phù hợp |
| **Phạt người báo blocker hoặc sai estimate** | Dữ liệu không còn trung thực | Khuyến khích nêu vấn đề sớm và học từ hệ thống |

### Lãnh đạo cần yêu cầu báo cáo gì?

Thay vì hỏi “tuần này team có tăng thêm 15 story points không?”, có thể hỏi:

- **Giá trị nào tới người dùng**, đã có bằng chứng gì?
- **Điều gì đang khiến công việc chờ**, và cấp quản lý có thể gỡ phụ thuộc nào?
- **Những giả định kế hoạch nào đã thay đổi**, cần quyết định trade-off nào?
- **Lỗi và rủi ro** được kiểm soát bằng cách nào?
- **Năng lực nhóm** đang tăng hay chỉ đang dùng thêm giờ để giao việc?
- **Thử nghiệm cải tiến** nào đã được đánh giá và quyết định giữ/sửa/dừng?

Đó là cách giữ trách nhiệm và minh bạch mà **không đánh đồng kiểm soát với giám sát từng phút làm việc**.

### Quyền tự chủ có giới hạn rõ

Product Owner cần không gian **sắp thứ tự Product Backlog theo giá trị**; Developers cần khả năng **chọn cách thực hiện và bảo vệ chất lượng**; Scrum Master/những người hỗ trợ flow cần khả năng **làm lộ và gỡ trở ngại hệ thống**. Nhưng tự chủ không có nghĩa bỏ trách nhiệm tuân thủ, hợp đồng hay an toàn dữ liệu.

### Khi deadline đến từ hợp đồng

Lãnh đạo phải minh bạch **những nghĩa vụ không được đổi**, giúp team sắp thứ tự scope và phân bổ năng lực phù hợp, xác định thời điểm đánh giá rủi ro và phương án khi forecast không đạt. Không được yêu cầu đội **hứa mọi thứ cùng lúc** rồi gọi đó là “Agile commitment”.

## 26. Những phản mẫu điển hình và cách sửa

### 26.1. “Agile là làm gấp mọi thứ”

Mọi yêu cầu được dán nhãn khẩn, không còn thứ tự thật. **Cách sửa:** phân biệt incident/nghĩa vụ bắt buộc với ý tưởng thường lệ; Product Owner ưu tiên theo giá trị và chi phí cơ hội.

### 26.2. “Không cần kế hoạch vì ngày mai còn thay”

Nhóm thiếu mục tiêu, ranh giới Done và dự báo. **Cách sửa:** lập kế hoạch theo độ bất định, cập nhật ngắn thường xuyên; giữ Product Goal/Sprint Goal hoặc policy flow rõ.

### 26.3. “Velocity phải tăng mỗi Sprint”

Khuyến khích ước lượng lại và làm thêm giờ. **Cách sửa:** dùng velocity tùy chọn cho forecast nội bộ cùng team, xem flow/quality/outcome và không so points giữa nhóm.

### 26.4. “Mọi người có ít nhất ba ticket Doing mới là hiệu quả”

WIP cao, chuyển ngữ cảnh và chờ review. **Cách sửa:** ưu tiên hoàn tất, quản lý WIP và xem work item age.

### 26.5. “Cắt test để đạt mốc nhanh”

Thời gian code có thể giảm nhưng lỗi và chi phí sửa tăng. **Cách sửa:** giữ DoD, test theo rủi ro, CI và release an toàn; đổi phạm vi khi cần.

### 26.6. “Definition of Done là PR merged”

Có thể phù hợp với một trạng thái kỹ thuật nội bộ nhưng chưa đủ điều kiện Increment thực. **Cách sửa:** xác nhận DoD theo sản phẩm và tổ chức, phân biệt merged/deploy/release/Done.

### 26.7. “Đã demo được là xong”

Demo dùng mock có thể che chưa tích hợp, chưa bảo mật hoặc chưa có dữ liệu thật. **Cách sửa:** Increment được kiểm chứng theo tiêu chuẩn, feedback sản phẩm có bối cảnh.

### 26.8. “Mọi thay đổi khách hàng phải vào Sprint ngay”

Sprint Goal bị phân tán. **Cách sửa:** phân loại mức khẩn, thương lượng scope trong giới hạn mục tiêu, đưa ý tưởng thường lệ vào Product Backlog.

### 26.9. “Không thay đổi gì cho tới hết Sprint”

Phản hồi có giá trị hoặc rủi ro an toàn bị bỏ qua. **Cách sửa:** kiểm tra và thích ứng liên tục; giữ mục tiêu nhưng điều chỉnh cách thực hiện khi học thêm.

### 26.10. “Sprint Planning chỉ là buổi giao task”

Không ai hiểu vì sao Sprint có giá trị. **Cách sửa:** trả lời Why/What/How và xây Sprint Goal chung.

### 26.11. “Daily Scrum là buổi điểm danh cho quản lý”

Nhóm không thực sự điều chỉnh kế hoạch. **Cách sửa:** Developers kiểm tra tiến triển tới Sprint Goal, làm rõ blockers và hành động phối hợp.

### 26.12. “Sprint Review là buổi công bố đã làm xong bao nhiêu điểm”

Không có phản hồi sản phẩm hay điều chỉnh backlog. **Cách sửa:** kiểm tra Increment, môi trường và giả định giá trị với bên liên quan.

### 26.13. “Retrospective là nơi hứa tăng 20% tốc độ”

Không có giả thuyết hoặc thay đổi hệ thống. **Cách sửa:** chọn một đòn bẩy cụ thể, có timebox, metric và guardrails.

### 26.14. “Càng nhiều lần deploy càng có giá trị”

Deploy không nhất thiết đi cùng feature exposure hay người dùng có lợi. **Cách sửa:** xem time-to-feedback, product outcome và reliability.

### 26.15. “Throughput cao nhất là team giỏi nhất”

Ticket nhỏ có thể làm số lượng lớn mà không tạo lát cắt hữu ích. **Cách sửa:** định nghĩa loại item, đo flow trong ngữ cảnh và đối chiếu chất lượng/giá trị.

### 26.16. “SLE 85% trong 10 ngày nghĩa là mọi item chắc chắn xong ngày thứ mười”

Hiểu sai xác suất và có thể phạt người giữ việc khó. **Cách sửa:** sử dụng SLE như kỳ vọng và tín hiệu quản lý age, không cam kết tuyệt đối.

### 26.17. “Không cần refinement để tiết kiệm thời gian”

Sai quy tắc được phát hiện khi code gần xong. **Cách sửa:** làm rõ story, ví dụ và phụ thuộc vừa đủ trước khi bắt đầu.

### 26.18. “Bắt đầu càng nhiều việc thì càng nhanh xong backlog”

Hàng chờ tăng, item cũ không hoàn tất. **Cách sửa:** pull policy, WIP control, swarming và xem end-to-end flow.

### 26.19. “Khi trễ thì thêm người là xong”

Điểm nghẽn có thể là một hợp đồng API hoặc quyền review, thêm người tăng chi phí phối hợp. **Cách sửa:** tìm blocker thực, mở rộng năng lực hoặc self-service đúng điểm.

### 26.20. “Agile cho phép bỏ mọi tài liệu”

Những thông tin cần giữ về contract, data migration, vận hành và quyết định bị mất. **Cách sửa:** tạo **tài liệu vừa đủ để dùng và cập nhật**, không viết tài liệu hình thức cũng không cố bỏ hết.

### 26.21. “Tốc độ quan trọng hơn sự bền vững của nhóm”

Mọi thành công dựa vào làm thêm giờ, người giỏi kiệt sức và lỗi tích lũy. **Cách sửa:** capacity thực, WIP, automation, học hỏi và chính sách incident hợp lý.

### 26.22. “Mọi team phải chạy cùng framework, cùng velocity”

Bỏ qua bối cảnh support, sản phẩm, rủi ro và năng lực. **Cách sửa:** chọn Scrum/Kanban/XP theo mục tiêu dòng giá trị, nhất quán về chất lượng chứ không ép số đo giống nhau.

### 26.23. “Kế hoạch đã thay là chứng minh nhóm lập kế hoạch kém”

Khuyến khích che thông tin mới. **Cách sửa:** phân biệt thay đổi do học hỏi hợp lý với thiếu chuẩn bị; xem giả thuyết và tốc độ phản hồi.

### 26.24. “KPI đẹp chứng minh Agile thành công”

Số liệu có thể đổi định nghĩa hoặc bị thao túng. **Cách sửa:** chuẩn hóa metric contract, xem dữ liệu nguồn, phân khúc, guardrails và quyết định sản phẩm thật.

## 27. Workshop 75–90 phút: chuyển từ “nhanh hơn” sang “giao giá trị tốt hơn”

Đây là một **bài thực hành gợi ý**, không phải một sự kiện bắt buộc của Scrum, Kanban hoặc XP. Mục tiêu là giúp nhóm **định nghĩa đúng vấn đề, chọn kế hoạch thích ứng và thiết kế cách kiểm chứng**, chứ không tạo thêm nghi thức.

### Tình huống

Nhóm Học tiếp có 11 work items đang Doing, 4 item chờ review hơn ba ngày làm việc, CI flaky và người học tiếp tục báo mở sai checkpoint. Lãnh đạo yêu cầu **tăng velocity 25% trong Sprint tới** và **giảm thời gian họp một nửa**.

| Bước | Thời lượng | Hoạt động | Đầu ra |
| --- | ---: | --- | --- |
| **1. Nhìn giá trị** | 10 phút | Viết người dùng nào đang gặp vấn đề và giá trị nào chưa đến | Problem statement gắn hành trình học |
| **2. Tách tín hiệu** | 10 phút | Phân loại activity, output, flow, quality, outcome | Không lấy velocity làm mục tiêu giá trị |
| **3. Vẽ workflow** | 15 phút | Chỉ ra start/finish, WIP, review queue, phụ thuộc và DoD | Bản đồ điểm chờ và rủi ro |
| **4. Chọn mục tiêu** | 10 phút | Viết Sprint Goal hoặc flow goal phù hợp và một giả thuyết sản phẩm | Định hướng rõ, không phải số ticket |
| **5. Lập kế hoạch vừa đủ** | 15 phút | Chọn một lát cắt, quality checks, phụ thuộc, capacity và chính sách pull | Kế hoạch ngắn có thể điều chỉnh |
| **6. Chọn cải tiến** | 10 phút | Thử WIP control, contract tests hoặc clarification sớm | Thí nghiệm có owner/timebox |
| **7. Thiết kế phép đo** | 10 phút | Chọn cycle time/age, quality và product outcome, guardrails | Metric contract và cửa sổ xem lại |
| **8. Giả lập thay đổi** | 5–10 phút | Stakeholder đưa yêu cầu mới hoặc có incident | Quy tắc triage, trade-off và quyết định |

### Câu hỏi cho nhóm thực hành

1. Tăng velocity 25% có trực tiếp giải quyết **sai checkpoint** không?
2. “Giảm họp 50%” có thể tốt khi nào và gây hại khi nào?
3. Nếu thời gian chờ review là nút thắt, nhóm cần **thêm người code hay giúp hoàn tất những item dở**?
4. Nếu một thay đổi về phân quyền có rủi ro cao, việc nào bắt buộc phải kiểm tra?
5. Khi marketing thêm một ý tưởng không khẩn giữa Sprint, **ai sắp thứ tự và điều kiện nhận ngay là gì**?
6. Nếu quality checks tăng thời gian xây feature đầu tiên nhưng giảm lỗi về sau, đánh giá “tốc độ” như thế nào?
7. Điều gì chứng minh người học **thực sự nhận giá trị**, khác với việc nút đã được deploy?

### Tiêu chí hoàn thành

Workshop đạt mục tiêu khi nhóm có:

- Một **vấn đề được xác nhận bằng bằng chứng**, không chỉ “làm việc hơi chậm”.
- Một mục tiêu liên quan **giá trị hoặc năng lực tạo giá trị**.
- Một kế hoạch **có phạm vi, phụ thuộc, chất lượng và chỗ có thể điều chỉnh**.
- Một thay đổi về **WIP, kỹ thuật hoặc phối hợp** với cơ chế rõ.
- Các chỉ số **flow + quality + product outcome + sustainability** phù hợp.
- Một cách xử lý thay đổi mới **không bỏ hết mục tiêu và cam kết**.
- Một mốc review ghi rõ **giữ, sửa hay dừng** dựa trên kết quả.

## 28. Bài tập tự kiểm tra và gợi ý đáp án

### Bài tập A — Phân loại hai ngộ nhận

Cho các phát biểu:

1. “Agile nghĩa là không phải viết kế hoạch vì yêu cầu sẽ đổi.”
2. “Sprint nào cũng phải tăng story points để chứng minh tiến bộ.”
3. “Khi API thay đổi, chúng ta phải cập nhật Sprint Backlog và kiểm tra tác động tới Sprint Goal.”
4. “Mọi người phải nhận thêm ticket mới ngay khi hoàn thành code.”
5. “Chúng ta có Product Goal, backlog được sắp thứ tự và forecast được cập nhật từ feedback.”

Phân loại **ngộ nhận tốc độ**, **ngộ nhận không kế hoạch** hoặc **thực hành phù hợp**, giải thích từng câu.

**Gợi ý:** (1) không kế hoạch, (2) và (4) ngộ nhận tốc độ, (3) và (5) phù hợp với lập kế hoạch thích ứng.

### Bài tập B — Velocity tăng nhưng giá trị giảm

Sprint 1 nhóm hoàn tất 10 stories × 3 points = 30 points. Sprint 2 có cùng loại việc nhưng đổi thang ước lượng thành 5 points, chỉ hoàn tất 9 stories và tăng lỗi hồi quy.

1. Velocity Sprint 2 là bao nhiêu?
2. Có thể nói năng suất tăng 50% không?
3. Cần thêm những bằng chứng gì?
4. Vì sao không nên thưởng cho nhóm có points cao hơn?

**Gợi ý:** Sprint 2 là \(9\times5=45\) points, tăng 50% về **con số points** nhưng thang ước lượng đổi, số stories ít hơn và lỗi tăng; **không có cơ sở kết luận năng suất hay giá trị tăng 50%**.

### Bài tập C — Median cycle time và rủi ro đuôi dài

Cycle time (ngày làm việc) của sáu items trước thay đổi:

~~~text
Trước: 3, 5, 7, 9, 12, 20
Sau:   3, 4, 6, 8, 11, 18
~~~

1. Median trước và sau là bao nhiêu?
2. Median giảm bao nhiêu ngày, phần trăm tương đối?
3. Vì sao cần xem item cuối có tuổi 18 ngày?
4. Số liệu này có chứng minh WIP policy là nguyên nhân không?

**Gợi ý:** Trước \((7+9)/2=8\) ngày; sau \((6+8)/2=7\) ngày. Giảm 1 ngày, tương đối \(1/8=12{,}5\%\). Mẫu nhỏ và còn item chậm; cần xem mix work items, blocked reasons, lỗi và các thay đổi đồng thời.

### Bài tập D — Dự báo khi không có ngày chắc chắn

Một workflow có throughput bốn tuần gần nhất **3, 5, 2, 6 items/tuần**. Còn 16 items tương tự trên backlog.

1. Trung bình throughput là bao nhiêu?
2. Nếu chia thô, thời gian ước lượng bằng bao nhiêu tuần?
3. Vì sao con số ấy không phải cam kết chắc chắn?
4. Nếu lịch khai giảng là mốc cứng, có những biến số nào phải thương lượng?

**Gợi ý:** Tổng 16 items/4 tuần = 4 items/tuần; chia thô 16/4 = 4 tuần. Lịch sử biến động và có phụ thuộc; cần làm rõ **scope, rủi ro, capacity, phương án dự phòng**, không bỏ DoD.

### Bài tập E — Khách hàng thêm việc giữa Sprint

Sprint Goal là “người học mở lại đúng bài an toàn”. Giữa Sprint, có ba yêu cầu:

1. Fix một lỗi checkpoint đang làm mất tiến độ production.
2. Thêm bảng xếp hạng bạn bè để chạy marketing tháng tới.
3. Làm rõ quy tắc khi một người có hai checkpoint.

Bạn sẽ xử lý từng việc như thế nào, với vai trò nào, và có cần thay Sprint Goal không?

**Gợi ý:** (1) xử lý incident ngay; (2) Product Owner đánh giá và sắp Product Backlog, không tự chen vào; (3) làm rõ và điều chỉnh kế hoạch cùng mục tiêu. Chỉ khi Sprint Goal trở nên lỗi thời mới xét hủy Sprint theo Scrum Guide, và **Product Owner** có thẩm quyền quyết định việc ấy.

### Bài tập F — Timebox và chất lượng

Một spike hai ngày đã khám phá hai phương án lưu checkpoint nhưng chưa chứng minh được an toàn khi nhiều thiết bị ghi đồng thời. Quản lý yêu cầu “đến hạn timebox phải coi tính năng Done”.

1. Timebox spike dùng để tạo ra kết quả gì?
2. Có thể chọn những hành động nào tiếp theo?
3. Vì sao chưa được gọi Increment Done?

**Gợi ý:** Spike tạo **bằng chứng/kiến thức**, không hứa production feature. Có thể thử thêm, giảm scope, thay thiết kế hoặc xin quyết định rủi ro; Increment chỉ Done khi đạt **Definition of Done**.

### Bài tập G — Phân biệt output và outcome

Phân loại:

1. “Đã deploy 12 lần.”
2. “95% API checks chạy đúng và đáng tin trong CI.”
3. “Người học đủ quyền mở đúng bài trong 60 giây thường xuyên hơn.”
4. “Team đóng 20 PBIs.”
5. “Lỗi mất dữ liệu thực tế được phát hiện/khôi phục sớm hơn.”

**Gợi ý:** (1), (4) là output/khả năng giao; (2) là bằng chứng kỹ thuật/quality diagnostic; (3) là product outcome; (5) là reliability outcome. Không một chỉ số đơn lẻ chứng minh toàn bộ impact.

### Bài tập H — Quá tải và giới hạn WIP

Một nhóm có 8 Developers và 16 features Doing. Hàng Review có 7 items, trong đó 3 items chờ hơn bốn ngày. Lãnh đạo muốn mỗi Developer bắt đầu thêm một story để “không ai rảnh”.

1. Vì sao thêm việc có thể làm chậm?
2. Đề xuất một thỏa thuận pull/review có thể thử.
3. Metrics và guardrails nào cần xem?
4. Có thể kết luận WIP limit 5 là đúng cho mọi team không?

**Gợi ý:** Chuyển ngữ cảnh và hàng chờ tăng; ưu tiên review/swarming, ghi age, cycle time, throughput, lỗi, cảm nhận workload; thử giới hạn theo bối cảnh, không mặc định con số.

### Bài tập I — Phân quyền và quyền sở hữu sản phẩm

Product Owner muốn ưu tiên sửa hành trình Học tiếp theo feedback, nhưng một manager gửi 10 việc mới yêu cầu làm ngay, còn Developers không được phép điều chỉnh task đã giao.

1. Những yếu tố nào chưa phù hợp với tinh thần Agile và Scrum?
2. Ai có trách nhiệm sắp Product Backlog?
3. Ai điều chỉnh Sprint Backlog?
4. Manager có thể gỡ trở ngại nào mà không điều khiển từng task?

**Gợi ý:** Cần làm rõ quyền PO, vai trò Developers, Sprint Goal, trade-off và cách triage. Manager có thể bảo vệ capacity, giải quyết phụ thuộc tổ chức, hỗ trợ chính sách minh bạch và bền vững.

### Bài tập J — Chất lượng so với deadline

Đến trước hạn khai giảng ba ngày, API Học tiếp vẫn chưa vượt qua một kiểm tra phân quyền quan trọng. Có người đề nghị tạm tắt kiểm tra để cho kịp.

1. Có nên bỏ kiểm tra không?
2. Những phương án điều chỉnh **phạm vi, exposure hoặc kế hoạch** có thể dùng?
3. Khi nào cần xử lý như incident?
4. Làm thế nào báo cho stakeholder mà không nói dối về trạng thái Done?

**Gợi ý:** Không bỏ guardrail bắt buộc; có thể chưa bật feature, giảm scope tới lát cắt đủ an toàn, dời release nếu được hoặc xin quyết định quản trị rủi ro phù hợp. Nếu đã có rò rỉ production, phản ứng theo incident policy ngay.

### Bài tập K — Cải thiện flow nhưng product outcome chưa đổi

Sau khi cải tiến CI và WIP, median cycle time giảm từ 12 xuống 8 ngày. Tuy nhiên, người học vẫn mở sai bài trên mobile.

1. Những năng lực nào có thể đã tiến bộ?
2. Vì sao chưa thể kết luận tính năng tạo giá trị?
3. Phản hồi định tính nào cần thu?
4. Product Backlog nên được điều chỉnh ra sao?

**Gợi ý:** Kỹ thuật và flow có tín hiệu tốt; cần xem task success mobile, usability, checkpoint và quyền. Giữ những cải tiến delivery hữu ích, nhưng **đổi giả thuyết/thiết kế sản phẩm** theo bằng chứng.

### Bài tập L — Viết lại câu yêu cầu “nhanh hơn”

Chuyển phát biểu:

> “Team Agile phải tăng 30% velocity, giảm họp và không cần lập kế hoạch xa.”

thành một **mục tiêu có thể kiểm chứng** với các trường:

~~~text
Người nhận giá trị:
Vấn đề thực:
Kết quả cần cải thiện:
Baseline / cách đo:
Phạm vi / timebox:
Giả thuyết thay đổi:
Guardrails:
Người quyết định:
Mốc xem lại:
~~~

**Gợi ý:** Chọn một dòng giá trị, ví dụ “giảm thời gian chờ tích hợp của PBIs tính năng tiến độ để có thể kiểm chứng với người học sớm hơn”, với WIP, cycle time, kiểm tra quyền, chất lượng và team load. Nếu chưa có baseline, nêu **cần đo**, không tự bịa mục tiêu 30%.

## 29. Checklist: Agile có đang bị biến thành “chạy nhanh/không kế hoạch”?

### A. Định hướng và lập kế hoạch

- [ ] Người tham gia giải thích được **vấn đề người dùng và mục tiêu giá trị** hiện tại.
- [ ] Có Product Goal hoặc định hướng sản phẩm tương đương, không chỉ danh sách ticket.
- [ ] Product Backlog được **sắp thứ tự và refinement** theo phản hồi.
- [ ] Nếu dùng Scrum, có **Sprint Goal rõ** và Sprint Backlog được Developers cập nhật khi học thêm.
- [ ] Nếu dùng Kanban, có **Definition of Workflow, pull policies, WIP control và tiêu chí hoàn tất**.
- [ ] Mức độ chi tiết kế hoạch phù hợp **bất định, phụ thuộc và rủi ro**.
- [ ] Các deadline/hợp đồng thực có **dự báo, phương án dự phòng và trade-off minh bạch**.
- [ ] Những yêu cầu mới có cơ chế triage, không tự động chen vào công việc đang dở.
- [ ] Thay đổi kế hoạch được giải thích bằng **bằng chứng và điều kiện**, không bị coi mặc định là thất bại.

### B. Chất lượng và năng lực giao hàng

- [ ] **Definition of Done** được hiểu và không bị hạ để đạt mốc báo cáo.
- [ ] Những rủi ro quyền truy cập, dữ liệu và an toàn được kiểm chứng đúng mức.
- [ ] Nhóm tạo **vertical slices** có thể dùng, không chỉ các task theo lớp kỹ thuật.
- [ ] Có **CI/tests/integration feedback sớm** phù hợp rủi ro.
- [ ] Release/rollout có cách kiểm tra và phản ứng khi guardrail bị vi phạm.
- [ ] Deploy, release, exposure và product outcome được **phân biệt**.
- [ ] Chất lượng và khả năng thay đổi được duy trì bằng refactoring và học hỏi khi cần.

### C. Flow và khả năng dự báo

- [ ] WIP và blocked items được nhìn thấy trung thực.
- [ ] Người làm không bị yêu cầu **luôn bận 100%** hoặc có nhiều ticket Doing.
- [ ] Nhóm có thỏa thuận **ưu tiên hoàn tất** khi hàng chờ đạt giới hạn.
- [ ] Cycle time, throughput và work item age có **định nghĩa nhất quán**.
- [ ] Xem phân bố và các trường hợp đuôi dài, không chỉ một con số trung bình.
- [ ] Forecast thể hiện **giả định, độ bất định, phạm vi và ngày xem lại**.
- [ ] SLE nếu dùng được hiểu như **kỳ vọng có xác suất**, không phải lời hứa tuyệt đối.
- [ ] Không so velocity/story points của các team như năng suất.

### D. Giá trị và phản hồi

- [ ] Có cách đo/quan sát người dùng thật, không dừng ở số tính năng phát hành.
- [ ] Chỉ số product outcome gắn với **tác vụ hoặc lợi ích thực**, không chỉ click/engagement.
- [ ] Phản hồi có thể làm đổi **Product Backlog, thiết kế và kế hoạch** khi phù hợp.
- [ ] Phân biệt activity, output, capability, outcome và impact trong báo cáo.
- [ ] Có xem **dữ liệu nguồn, mẫu số, cohort và giới hạn nhân quả** trước khi kết luận.
- [ ] Những giả thuyết không được xác nhận có thể được **dừng hoặc sửa** thay vì ép triển khai.

### E. Con người và quản trị

- [ ] Có thể công khai blocker, lỗi và bất định mà không bị trừng phạt vì số liệu.
- [ ] Không dùng velocity, số commit/ticket hoặc giờ trực tuyến để xếp hạng cá nhân.
- [ ] Capacity bao gồm review, kiểm thử, hỗ trợ, học kỹ thuật và công việc không dự kiến.
- [ ] Không dựa vào làm thêm giờ kéo dài để “đạt tốc độ”.
- [ ] Product Owner, Developers, Scrum Master và lãnh đạo hiểu quyền/trách nhiệm phù hợp.
- [ ] Phụ thuộc xuyên nhóm có owner và đường escalation, không bị giấu ngoài board.
- [ ] Có chu kỳ **cải tiến dựa trên kết quả**, không chỉ lời hứa “cố nhanh hơn”.
- [ ] Tổ chức sẵn sàng **giữ, sửa hoặc bỏ** một chính sách không tạo ra kết quả mong muốn.

**Nếu nhiều ô không đạt, không cần quy kết “nhóm không đủ Agile”.** Nên chọn **một rào cản có tác động lớn**, thiết kế thử nghiệm an toàn và đánh giá theo dữ liệu để cải thiện hệ thống.

## 30. Hỏi đáp nhanh khi gặp hai ngộ nhận

### Agile có phải làm nhiều tính năng hơn trong cùng một khoảng thời gian?

**Không nhất thiết.** Khả năng giao giá trị sớm hơn có thể đến từ **làm ít việc nhưng đúng thứ tự**, chia lát cắt nhỏ và giảm rework/chờ đợi. Tổng số tính năng hoặc ticket không phải giá trị tự thân.

### Agile có cấm kế hoạch dài hạn không?

**Không.** Có thể có Product Goal, roadmap, mục tiêu phát hành, kế hoạch đầu tư và forecast dài hạn. Chỉ cần **làm rõ điều nào chắc, điều nào chưa biết và khi nào cần cập nhật**. Kế hoạch dài hạn càng chi tiết và bất biến trong môi trường bất định càng có nguy cơ sai.

### Scrum có bắt hoàn thành tất cả PBIs đã chọn trong Sprint không?

Scrum Team hướng tới **Sprint Goal**, Developers lựa chọn công việc và lập kế hoạch để có Increment đạt DoD. Sprint Backlog được cập nhật khi học thêm; phạm vi có thể thương lượng lại với Product Owner miễn **không đe dọa Sprint Goal và không giảm chất lượng**. Không xem PBIs như lời hứa số điểm tuyệt đối.

### Nếu trong Sprint phát hiện việc mới có giá trị cao thì sao?

Đánh giá mức khẩn, ảnh hưởng tới Sprint Goal, rủi ro và chi phí cơ hội; **ý tưởng thường lệ** đi qua Product Backlog, còn **sự cố nghiêm trọng** theo đường xử lý khẩn. Nếu Sprint Goal trở nên lỗi thời, Product Owner có thẩm quyền hủy Sprint theo Scrum Guide.

### Kanban có nghĩa chỉ kéo việc, không cần dự báo?

**Không.** Kanban có chính sách workflow, WIP, replenishment và SLE, giúp ra quyết định/dự báo dựa trên dòng thực. Không có Sprint cố định không đồng nghĩa không có kế hoạch.

### XP có làm team chậm đi vì viết test trước?

Một phần công việc đầu có thể cần thêm thời gian cho tests, nhưng mục đích là **rút ngắn feedback, giảm hồi quy và chi phí thay đổi**. Phải đo kết quả trong hệ thống thực: chất lượng, rework, time-to-feedback và khả năng giao an toàn. Không phải mọi công việc đều cần áp TDD cùng cách.

### Nếu deadline không thể dời, có phải hy sinh quality?

**Không.** Nên ưu tiên phạm vi thiết yếu, kiểm tra điều kiện bắt buộc, dự báo và công khai rủi ro. Nếu không thể giao an toàn, nói rõ giới hạn và cần quyết định phù hợp, không đổi nghĩa Done.

### Một team luôn đạt velocity cao nhưng người dùng không hài lòng thì sao?

Điều đó cho thấy **metric hiện tại không đủ để đánh giá giá trị**. Cần nghiên cứu nhu cầu, định nghĩa outcome và kiểm tra xem backlog có đang chọn đúng vấn đề không. Có thể giữ những năng lực delivery hữu ích nhưng đổi hướng sản phẩm.

### Có thể biết Agile “nhanh hơn” bằng một con số không?

**Không nên chỉ một số.** Xem kết hợp **thời gian tới giá trị, chất lượng, flow, mức bất định và nhịp bền vững**, theo ranh giới phù hợp. Mục tiêu là quyết định tốt và cải tiến, không tạo một bảng xếp hạng.

## 31. Tài liệu đọc thêm và tổng kết

- [Agile Manifesto](https://agilemanifesto.org/): bốn giá trị, đặc biệt phản hồi thay đổi thay vì bám cứng kế hoạch.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm hoạt động thường xuyên, phát triển bền vững, kỹ thuật tốt, đơn giản và suy ngẫm/cải tiến.
- [The Scrum Guide](https://scrumguides.org/): Product Goal, Sprint Goal, Product/Sprint Backlog, Definition of Done, Sprint Planning, Daily Scrum, Sprint Review và Retrospective.
- [The Kanban Guide](https://kanbanguides.org/): Definition of Workflow, WIP, throughput, work item age, cycle time và Service Level Expectation.
- Kent Beck và Cynthia Andres, *Extreme Programming Explained: Embrace Change*, ấn bản 2 (2004): small releases, CI, TDD, pairing, refactoring và phát triển bền vững.
- Mary và Tom Poppendieck, *Lean Software Development: An Agile Toolkit* (2003): tối ưu hệ thống thay vì mức bận cá nhân, chất lượng và loại bỏ lãng phí.
- Donald G. Reinertsen, *The Principles of Product Development Flow* (2009): hàng đợi, kích thước lô, biến thiên, kinh tế của dòng phát triển sản phẩm.
- Jez Humble và David Farley, *Continuous Delivery* (2010): kiểm tra và triển khai những thay đổi nhỏ một cách an toàn.
- [DORA](https://dora.dev/): nghiên cứu về năng lực giao phần mềm và reliability, giúp phân biệt engineering performance với product outcomes.
- Troy Magennis, *Forecasting and Simulating Software Development Projects* (2011): sử dụng dữ liệu lịch sử, biến thiên và mô phỏng để dự báo; cần xác minh phương pháp phù hợp bối cảnh.
- Jeff Patton, *User Story Mapping* (2014): chia lát cắt theo hành trình người dùng và ưu tiên giá trị.

### Tổng kết

**Thứ nhất:** Agile không đồng nghĩa **làm việc với cường độ cao**. Số story points, số ticket, số commit hay tỷ lệ người luôn bận không đo được giá trị sản phẩm. Nhịp làm việc bền vững, chất lượng kỹ thuật và khả năng hoàn tất lát cắt quan trọng hơn việc bắt đầu thật nhiều việc.

**Thứ hai:** Agile không đồng nghĩa **thiếu kế hoạch**. Product Goal, backlog, Sprint Goal, Definition of Done, chính sách Kanban, forecast và release plan giúp nhóm có định hướng và phối hợp. Kế hoạch tốt **được cập nhật khi học thêm**, không được coi là chân lý bất biến.

**Thứ ba:** Tốc độ cần được hiểu là **thời gian tới phần mềm đúng, có thể dùng, nhận feedback và tạo giá trị**, trong giới hạn an toàn. Flow metrics, chất lượng và product outcome phải được đọc **cùng nhau**, không dùng một chỉ số ép con người.

**Thứ tư:** Khi có thay đổi, hãy **triage, làm rõ tác động, thương lượng phạm vi và điều chỉnh kế hoạch một cách có trách nhiệm**, thay vì nhận mọi việc hoặc từ chối mọi phản hồi. Với rủi ro nghiêm trọng, cần hành động ngay; với ý tưởng thường lệ, backlog và mục tiêu giúp chọn đúng thứ tự.

**Điểm cần nhớ:** **Agile là khả năng thích ứng có kỷ luật, không phải hỗn loạn có tốc độ cao.** Một nhóm Agile giỏi không nhất thiết luôn làm nhiều việc hơn; họ **biết điều gì quan trọng, hoàn thành an toàn, học sớm, thay đổi hướng đúng lúc và tiếp tục cải tiến**.
