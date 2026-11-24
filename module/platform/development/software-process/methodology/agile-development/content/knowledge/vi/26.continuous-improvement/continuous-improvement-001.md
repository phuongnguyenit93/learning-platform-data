# Tạo vòng cải tiến từ quan sát, giả thuyết đến thử nghiệm

## 1. Vì sao Agile cần một vòng cải tiến có kiểm chứng?

Một nhóm có thể tổ chức Retrospective sau mỗi Sprint, ghi rất nhiều ý tưởng rồi vẫn gặp lại cùng một vấn đề: Pull Request chờ review lâu, kiểm thử tích hợp dồn cuối Sprint, nhiều yêu cầu bị chặn, người học không hoàn tất đăng ký khóa học. Nguyên nhân không nhất thiết là thiếu nỗ lực. Có thể nhóm mới dừng ở **nêu ý kiến và quyết định giải pháp**, chưa kiểm tra xem giải pháp có tác dụng hay không.

Ví dụ, trong một nền tảng học trực tuyến, nhóm nhận thấy:

- Nhiều học viên nhấn nút đăng ký hai lần vì không rõ phản hồi.
- Nhân viên hỗ trợ thường xuyên phải tra trạng thái thay người học.
- Thời gian từ bắt đầu phát triển đến khi một lát cắt đăng ký đạt Done tăng.
- Một số thành viên cho rằng cần thêm nhân sự, người khác cho rằng cần sửa CI.

Nếu lập tức tuyển người, thay công nghệ hoặc thêm cuộc họp, nhóm có thể giải quyết **một giả thuyết chưa được kiểm chứng** thay vì vấn đề thật.

**Vòng cải tiến liên tục** là quá trình lặp:

1. Quan sát trạng thái công việc, sản phẩm và kết quả người dùng.
2. Mô tả khoảng cách giữa hiện tại và trạng thái mong muốn.
3. Xây giả thuyết về nguyên nhân hoặc cơ chế cải thiện.
4. Chọn thử nghiệm nhỏ, có kiểm soát và có khả năng học hỏi.
5. Thu bằng chứng, so sánh với dự đoán ban đầu.
6. Quyết định duy trì, điều chỉnh, hoàn tác hoặc thử giả thuyết khác.
7. Đưa hiểu biết mới trở lại cách làm và tiếp tục quan sát.

Trong module **AGILE_DEVELOPMENT**, tư duy này giúp kết nối giá trị Agile — **phản hồi sớm, giao sản phẩm tăng dần và thích ứng liên tục** — với thực hành user story, backlog, Scrum, Kanban, XP và đo lường luồng công việc.

> **Thông điệp cốt lõi:** Cải tiến không phải số lượng ý tưởng được nêu ra, cuộc họp đã tổ chức hay công cụ mới đã mua. Cải tiến là **một thay đổi có bằng chứng cho thấy hệ thống làm việc hoặc kết quả người dùng tốt hơn**, đồng thời không gây ra tác hại không chấp nhận được.

### 1.1. “Liên tục” không có nghĩa thay đổi mọi thứ mỗi ngày

Một vòng học hỏi có thể kéo dài vài giờ khi xử lý test không ổn định, vài ngày khi giảm thời gian chờ review hoặc nhiều tuần khi xem hiệu quả một thay đổi hành trình người học. Nhịp phù hợp phụ thuộc:

- Tốc độ có thể quan sát kết quả.
- Mức rủi ro khi thử nghiệm.
- Kích thước thay đổi.
- Mức phụ thuộc liên nhóm.
- Số lượng trường hợp đủ để rút ra nhận định thận trọng.
- Các nghĩa vụ về dữ liệu, bảo mật và an toàn.

**Thử nhanh** không đồng nghĩa **quyết vội**. Với hành vi có thể gây mất tiền, lộ dữ liệu hoặc ảnh hưởng an toàn, nhóm phải dùng các biện pháp kiểm chứng và quyền quyết định tương xứng.

## 2. Bản đồ tổng thể: từ quan sát tới hành động tiếp theo

~~~mermaid
flowchart TD
    A["Quan sát dữ liệu và công việc thực"] --> B["Mô tả vấn đề và trạng thái mong muốn"]
    B --> C["Nêu giả thuyết có thể kiểm chứng"]
    C --> D["Thiết kế thử nghiệm nhỏ, an toàn"]
    D --> E["Thực hiện, ghi lại kết quả"]
    E --> F["So với dự đoán và guardrails"]
    F --> G{"Đã học được gì?"}
    G -- "Có bằng chứng cải thiện" --> H["Duy trì / chuẩn hóa, tiếp tục theo dõi"]
    G -- "Không cải thiện hoặc gây hại" --> I["Hoàn tác / điều chỉnh"]
    G -- "Chưa đủ bằng chứng" --> J["Thu thêm dữ liệu / thiết kế thử khác"]
    H --> A
    I --> B
    J --> C
~~~

Mô hình trên là **vòng suy nghĩ và phản hồi**, không phải quy trình phê duyệt tuần tự. Trong thực tế, nhóm có thể quay lại định nghĩa vấn đề ngay khi thấy một chỉ số không đo điều họ nghĩ.

### 2.1. Liên hệ với PDCA và PDSA

**Plan–Do–Check–Act (PDCA)** là một chu trình cải tiến thường dùng trong Lean:

| Bước | Câu hỏi | Bằng chứng hoặc đầu ra |
| --- | --- | --- |
| **Plan** | Vấn đề thật là gì, vì sao nghi nó xảy ra, muốn thử điều gì và đo thế nào? | Hiện trạng, giả thuyết, kế hoạch thử, ngưỡng đánh giá và giới hạn an toàn. |
| **Do** | Thực hiện thử nghiệm được kiểm soát ra sao? | Phạm vi thử, ngày bắt đầu, thay đổi đã thực hiện, ngoại lệ. |
| **Check** | Kết quả quan sát có khớp dự đoán không? Có tác động phụ không? | Dữ liệu, phản hồi định tính, rủi ro và mức bất định. |
| **Act** | Giữ, chuẩn hóa, sửa, hoàn tác hay thử tiếp? | Quyết định có lý do, owner, hành động kế tiếp. |

Biến thể **Plan–Do–Study–Act (PDSA)** nhấn mạnh **Study — nghiên cứu kết quả và học hỏi** thay vì hiểu “Check” như một thao tác đánh dấu đạt/không đạt. Hai cách gọi đều có thể giúp nhóm thực hành, miễn là **đối chiếu kết quả thật với dự đoán trước khi hành động tiếp**.

### 2.2. Liên hệ với Build–Measure–Learn

Trong khám phá sản phẩm, một vòng **Build–Measure–Learn** tập trung kiểm tra giả định giá trị hoặc hành vi:

- **Build:** đưa ra cách kiểm tra giả định, có thể là prototype, Increment nhỏ, thử nghiệm giao diện hoặc thay đổi dịch vụ.
- **Measure:** quan sát hành vi/kết quả với phép đo phù hợp.
- **Learn:** giữ giả thuyết, điều chỉnh hướng tiếp cận hoặc thay đổi chiến lược.

Không nhất thiết phải viết phần mềm production để học một điều. Có thể dùng phỏng vấn không dẫn dắt, thử prototype với dữ liệu giả hoặc phân tích lịch sử công việc. Nhưng nếu cần kiểm chứng tính đúng đắn kỹ thuật trong điều kiện thực, **một demo giả lập không đủ**.

### 2.3. Hai vòng có thể diễn ra song song

| Vòng cải tiến | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Vòng sản phẩm (outcome)** | Người dùng có nhận giá trị tốt hơn không? | Thêm khả năng tra trạng thái có giảm số học viên phải hỏi support không? |
| **Vòng cách làm (process/flow)** | Nhóm có tạo giá trị tin cậy với ít chờ đợi và làm lại hơn không? | Giới hạn WIP và review sớm có giảm cycle time mà không tăng lỗi không? |

Hai vòng liên quan nhưng **không đồng nhất**. Nhóm có thể tối ưu tốc độ hoàn tất ticket mà vẫn làm một tính năng ít người dùng. Ngược lại, một sản phẩm có nhu cầu cao vẫn có thể liên tục bị sự cố vì chất lượng vận hành chưa đủ.

## 3. Quan sát: bắt đầu bằng bằng chứng chứ không phải giải pháp yêu thích

### 3.1. Có thể quan sát những gì?

Một bản quan sát tốt kết hợp nhiều nguồn:

| Nguồn | Câu hỏi giúp trả lời | Ví dụ Agile |
| --- | --- | --- |
| **Bảng Kanban/Sprint Backlog** | Công việc đang nằm ở đâu, cái gì bị chặn, có quá nhiều việc dở không? | Ba PBI nằm ở Verify nhiều ngày. |
| **Dấu vết CI và code review** | Build, test, merge hoặc review đang gây chờ/làm lại ra sao? | PR chờ review chiếm phần lớn thời gian. |
| **Metrics flow** | Cycle time, throughput, WIP, work item age đang biến động thế nào? | Các item lâu nhất đều phụ thuộc môi trường tích hợp. |
| **Metrics sản phẩm/vận hành** | Người dùng hoàn tất tác vụ chưa; có lỗi dữ liệu, bảo mật, sự cố không? | Nhiều request timeout nhưng DB đã ghi thành công. |
| **Phản hồi support** | Người dùng đang cần trợ giúp về vấn đề lặp nào? | Học viên hỏi “đã đăng ký thành công chưa?”. |
| **Phỏng vấn/quan sát người dùng** | Họ thực sự làm gì và hiểu điều gì? | Học viên tưởng nút không phản hồi nên nhấn lại. |
| **Trao đổi với người làm** | Quyết định hoặc phụ thuộc nào gây khó mà dữ liệu định lượng chưa thể hiện? | Người kiểm thử chờ cấp dữ liệu an toàn. |
| **Sự cố và hậu kiểm** | Những điều kiện nào góp phần tạo lỗi hoặc làm phát hiện muộn? | Alert thiếu tín hiệu dữ liệu nhất quán. |

Một chỉ số riêng lẻ hiếm khi cho biết nguyên nhân. **Cycle time tăng** có thể vì item lớn hơn, WIP cao, môi trường test hỏng, review chậm hoặc tiêu chí Done được nâng cao. Quan sát giúp đặt câu hỏi, không tự sinh ra kết luận nhân quả.

### 3.2. Gemba: xem công việc ở nơi nó thực sự diễn ra

Trong Lean, *gemba* nhắc nhóm tới nơi công việc/giá trị thực sự được tạo ra. Trong phần mềm có thể là:

- Xem học viên thử đăng ký trên môi trường được phép.
- Quan sát nhân viên support xử lý một ticket với dữ liệu đã được bảo vệ.
- Cùng Developers xem trace CI và cách chờ review.
- Theo một PBI từ lúc được bắt đầu đến khi đủ điều kiện Done.
- Cùng vận hành đọc tín hiệu ứng cứu sự cố.

**Gemba không phải đi giám sát để tìm lỗi cá nhân.** Mục đích là hiểu tình trạng thực, điều gì người làm cần và nơi có cơ hội cải tiến. Phải tôn trọng quyền truy cập, sự đồng ý của người tham gia và riêng tư dữ liệu.

### 3.3. Phân biệt sự kiện, diễn giải và giả thuyết

| Mức | Ví dụ | Cách ghi |
| --- | --- | --- |
| **Sự kiện quan sát** | “Trong 12 PR gần nhất, 7 PR chờ reviewer quá một ngày làm việc.” | Nêu mẫu, khoảng đo và quy tắc tính. |
| **Diễn giải ban đầu** | “Review có thể là một điểm nghẽn.” | Ghi rõ là nhận định, chưa phải nguyên nhân chắc chắn. |
| **Giả thuyết cơ chế** | “Chỉ một reviewer có quyền chấp thuận tạo hàng đợi.” | Đưa ra bằng chứng nào có thể xác nhận hoặc bác bỏ. |
| **Đề xuất thử nghiệm** | “Có reviewer dự phòng và chọn PR nhỏ để review sớm.” | Giới hạn phạm vi, đo tác động, xem rủi ro chất lượng. |

Câu “mọi người thiếu chủ động” không phải bản mô tả vấn đề tốt vì **khó kiểm chứng và dễ đổ lỗi**. Câu “PR đã sẵn sàng review nhưng chờ trung vị 28 giờ trong hai tuần qua” cụ thể hơn nhiều.

### 3.4. Quan sát định tính không kém giá trị

Các ý kiến như **“Tôi không dám báo test đỏ vì sợ trễ Sprint”** hoặc **“Thông báo thành công không rõ nghĩa”** có thể là tín hiệu quan trọng chưa được phản ánh trong metrics. Nhóm nên ghi nguồn và ngữ cảnh, tránh suy một câu trả lời thành sự thật cho mọi người.

Có thể kết hợp:

- **Dữ liệu định lượng** để thấy kích thước hoặc xu hướng vấn đề.
- **Dữ liệu định tính** để hiểu cơ chế, bối cảnh và những tác động ngoài dự kiến.
- **Kiểm tra thực tế** bằng quan sát, thử nghiệm, tài liệu hoặc log liên quan.

Đặc biệt với đội nhỏ, dữ liệu mẫu ít nên tránh những kết luận thống kê mạnh khi chưa có đủ quan sát.

## 4. Định nghĩa vấn đề và trạng thái mục tiêu

### 4.1. Từ triệu chứng chung chung tới một khoảng cách rõ

Một câu nói như **“quy trình chậm”** có thể được làm rõ theo năm câu hỏi:

1. **Ai** bị ảnh hưởng: học viên, đội phát triển, support hay nhiều nhóm?
2. **Trong hoàn cảnh nào** vấn đề xuất hiện?
3. **Hiện trạng** có bằng chứng gì?
4. **Trạng thái mong muốn** là gì và phục vụ giá trị nào?
5. **Giới hạn nào không được đánh đổi:** DoD, bảo mật, riêng tư, dữ liệu, sức khỏe nhóm?

Ví dụ:

> Trong ba tuần gần đây, 8 trong 14 PBI được bắt đầu phải chờ kiểm thử tích hợp hơn hai ngày làm việc. Việc chờ làm nhóm có ít Increment đáp ứng DoD trước Sprint Review. Chúng ta muốn giảm thời gian chờ ở Verify trong các lát cắt tương đương, **không** bỏ kiểm thử bắt buộc hoặc chuyển lỗi sang production.

Đây là mô tả **vấn đề**, chưa khẳng định nguyên nhân hay giải pháp.

### 4.2. Phân biệt mục tiêu cải tiến với biện pháp

| Câu phát biểu | Thuộc loại nào? | Nhận xét |
| --- | --- | --- |
| “Cài thêm công cụ quản lý test.” | Giải pháp/hoạt động. | Chưa biết có giải quyết điểm nghẽn nào. |
| “Giảm thời gian chờ của PBI ở bước Verify mà không tăng lỗi sau phát hành.” | Kết quả mong muốn. | Có thể đo và thảo luận đánh đổi. |
| “Mỗi thành viên phải mở hai PR mỗi ngày.” | Chỉ tiêu hoạt động cá nhân. | Dễ tạo PR giả, không đại diện giá trị. |
| “Học viên tự xác minh được trạng thái đăng ký khi mất phản hồi mạng.” | Kết quả sản phẩm. | Tập trung hành vi người dùng cần thiết. |
| “Tổ chức thêm hai buổi họp/tuần.” | Giải pháp được đề xuất. | Có thể làm tăng gián đoạn nếu nguyên nhân không phải thiếu trao đổi. |

Một mục tiêu tốt không nhất thiết có ngay một con số chính xác. Nhóm có thể bắt đầu bằng **mức mong muốn và cách tìm dữ liệu nền**. Không nên đặt ngưỡng ngẫu nhiên chỉ để mục tiêu trông “SMART”.

### 4.3. Bản ghi vấn đề trước khi phân tích nguyên nhân

~~~text
Mã vấn đề: IMP-EXAMPLE-01
Hành trình giá trị: học viên tự đăng ký khóa miễn phí
Nhóm bị ảnh hưởng: học viên, support và Developers
Hiện tượng: nhiều phản ánh "không rõ đăng ký đã thành công"
Hiện trạng đã biết: tỷ lệ ticket cùng chủ đề trong kỳ quan sát
Điều chưa biết: có bao nhiêu request đã ghi nhưng mất phản hồi?
Trạng thái mong muốn: học viên biết trạng thái thật sau retry/timeout
Ranh giới: không tạo đăng ký trùng; không lộ dữ liệu học viên
Người cùng phân tích: PO, Developers, kiểm thử, support, vận hành
Nguồn bằng chứng: ticket đã loại dữ liệu nhạy cảm, log hợp lệ,
                 thử tác vụ với người dùng được đồng ý
~~~

Đây là **mẫu minh họa**, không phải ticket đã ghi trong hệ thống thật. Việc ghi **“điều chưa biết”** là quan trọng vì giúp nhóm tránh diễn giải giả định như sự thật.

## 5. Phân tích nguyên nhân: tìm cơ chế chứ không tìm người chịu lỗi

### 5.1. Triệu chứng có thể có nhiều nguyên nhân

Một PBI chờ lâu không nhất thiết vì “developer chậm”:

~~~mermaid
flowchart TD
    A["PBI chờ Verify lâu"] --> B["Môi trường test chưa sẵn sàng"]
    A --> C["Chỉ một người có quyền review"]
    A --> D["Test khó tái hiện / flaky"]
    A --> E["Lát cắt quá lớn hoặc phụ thuộc API"]
    A --> F["Yêu cầu chưa rõ / làm lại"]
    A --> G["WIP cao / đổi ngữ cảnh nhiều"]
~~~

Sơ đồ là một **bản đồ các khả năng cần điều tra**, không phải bằng chứng cho nguyên nhân nào đã xảy ra. Để chọn đối sách, nhóm phải xác minh bằng dữ liệu phù hợp.

### 5.2. Five Whys và giới hạn

**Five Whys** là cách liên tục hỏi vì sao từ hiện tượng tới các điều kiện bên dưới. Không có quy tắc phải đúng năm lần; các hệ thống phức tạp thường có **nhiều nguyên nhân cùng lúc**, nên đừng cố ép một “root cause” duy nhất.

Ví dụ giả thuyết cho việc test tích hợp xuất hiện muộn:

| Câu hỏi | Giả thuyết cần kiểm chứng |
| --- | --- |
| Vì sao cuối Sprint mới biết lỗi API? | Các thành phần chỉ được ghép sau khi từng tầng “xong”. |
| Vì sao ghép muộn? | Backlog được chia theo backend–frontend–QA thay vì lát cắt dọc. |
| Vì sao chia như vậy? | Nhóm dự báo theo năng lực chuyên môn riêng lẻ và chưa làm rõ hành vi tích hợp từ đầu. |
| Vì sao chưa trao đổi từ đầu? | Lịch refinement có ít người kiểm thử/đầu mối API. |
| Vì sao không thấy vấn đề sớm? | Flow metrics chưa phân biệt thời gian đang làm và chờ tích hợp. |

Đây **không phải kết luận**. Nhóm cần xem lịch sử PR, PBI, môi trường, điều kiện Done và phỏng vấn người thực hiện để kiểm tra các mắt xích.

### 5.3. Biểu đồ nhân–quả và hệ thống nhiều yếu tố

Với vấn đề phức tạp, nhóm có thể nhóm giả thuyết theo:

- **Quy tắc sản phẩm:** acceptance criteria, phạm vi và quyền quyết định.
- **Thiết kế/kiến trúc:** coupling, hợp đồng API, concurrency, dữ liệu.
- **Kỹ thuật:** CI, test, review, môi trường, cấu hình.
- **Luồng công việc:** WIP, phụ thuộc, batch size, chính sách chuyển trạng thái.
- **Con người và giao tiếp:** kỹ năng, khả năng xin giúp, cách chia sẻ thông tin.
- **Tổ chức:** ưu tiên thay đổi, thời gian chờ phê duyệt, quyền truy cập.
- **Người dùng và bối cảnh:** tải, hành vi thực tế và giả định thị trường.

Không dùng danh sách trên để tạo một cuộc điều tra vô hạn. Hãy chọn **một số giả thuyết có bằng chứng ban đầu và khả năng kiểm chứng**, đồng thời bảo vệ những rủi ro quan trọng.

### 5.4. Tránh kết luận quy lỗi

| Câu kết luận dễ gây phòng thủ | Câu hỏi hữu ích hơn |
| --- | --- |
| “QA chậm nên Sprint thất bại.” | “Bước Verify chờ gì và có thể bắt đầu kiểm chứng sớm hơn không?” |
| “Dev không chịu viết test.” | “DoD, thời gian, môi trường và kỹ năng nào khiến test chưa được thực hiện?” |
| “PO liên tục đổi yêu cầu.” | “Phần nào là làm rõ cam kết cũ, phần nào là thay đổi phạm vi; quyết định ưu tiên ra sao?” |
| “Support gửi ticket thiếu thông tin.” | “Mẫu ticket/công cụ nào giúp thu đúng bằng chứng mà không lấy dữ liệu nhạy cảm?” |
| “Người dùng nhấn hai lần nên lỗi dữ liệu.” | “Tại sao hệ thống không an toàn trước thao tác lặp có thể dự đoán?” |

Tôn trọng con người và **an toàn tâm lý** giúp những người nhìn thấy vấn đề lên tiếng sớm. Điều đó không xóa trách nhiệm chuyên môn hoặc nghĩa vụ sửa lỗi: mỗi hành động vẫn phải có chủ sở hữu và kết quả cần kiểm chứng.

## 6. Xây giả thuyết có thể bác bỏ

### 6.1. Giả thuyết khác giải pháp

Một giả thuyết tốt mô tả **một cơ chế có thể kiểm tra**. Ví dụ:

> Chúng tôi cho rằng PBI bị chờ Verify lâu **vì các thành phần chỉ tích hợp ở cuối**, nên nếu nhóm chia lát cắt nhỏ và chạy integration test từ sớm thì thời gian chờ Verify sẽ giảm, với điều kiện không bỏ bước kiểm thử bắt buộc.

Các thành phần của giả thuyết:

1. **Vấn đề:** thời gian chờ Verify cao.
2. **Cơ chế nghi ngờ:** tích hợp muộn tạo lỗi dồn cục và hàng đợi.
3. **Thay đổi thử:** chia lát cắt nhỏ, tích hợp/kiểm tra sớm.
4. **Dự đoán:** giảm thời gian chờ ở Verify.
5. **Điều kiện an toàn:** lỗi sau phát hành và DoD không bị xấu đi.

Câu “Chúng ta nên mua công cụ X” không phải giả thuyết đầy đủ. Nó chỉ nêu hành động; **không cho biết vì sao hành động có ích và bằng chứng nào sẽ khiến nhóm đổi ý**.

### 6.2. Mẫu giả thuyết thực hành

~~~text
Chúng tôi quan sát:
  [hiện tượng được đo hoặc xác minh] trong [phạm vi, thời gian].

Chúng tôi giả định nguyên nhân/cơ chế:
  [giải thích có thể sai].

Nếu thử:
  [một thay đổi cụ thể, trong phạm vi và khoảng thời gian rõ],

thì dự đoán:
  [tín hiệu hoặc kết quả sẽ thay đổi theo hướng nào],

vì:
  [cơ chế tác động được kỳ vọng].

Chúng tôi sẽ dùng:
  [metric chính, định nghĩa, dữ liệu nền, cách so sánh],

và bảo vệ:
  [guardrails như DoD, lỗi dữ liệu, an toàn, workload].

Nếu không thấy [dự đoán] hoặc guardrail vi phạm,
  chúng tôi sẽ [xem lại giả thuyết / hoàn tác / đổi thử nghiệm].
~~~

### 6.3. Ba ví dụ giả thuyết Agile

| Tình huống | Giả thuyết kiểm chứng được | Tín hiệu chính | Guardrail |
| --- | --- | --- | --- |
| PR chờ review lâu | Có người review dự phòng sẽ giảm thời gian chờ khi reviewer chính bận. | Thời gian từ “ready for review” tới review có ích. | Lỗi hậu merge, chất lượng review, tải người review. |
| Đăng ký timeout gây gọi support | Cách tự tra trạng thái thật sau timeout sẽ giảm nhu cầu hỏi support. | Tỷ lệ học viên xác minh được trạng thái mà không mở ticket. | Đăng ký trùng, lộ dữ liệu, sai trạng thái. |
| PBI dở dang tăng | Giảm WIP và tập trung hoàn tất sẽ giảm work item age của item đang chờ. | Work item age, cycle time theo loại việc. | Throughput, lỗi, tải công việc và việc khẩn. |

**Cơ chế phải hợp lý nhưng chưa được coi là sự thật.** Nếu không có thay đổi đúng như dự đoán, nhóm cần học điều gì đã sai: cơ chế, cách triển khai, cách đo hay bối cảnh.

### 6.4. Thế nào là có thể bác bỏ?

Một giả thuyết như **“công cụ mới sẽ làm nhóm tốt hơn”** rất khó bác bỏ vì “tốt hơn” không có định nghĩa. Giả thuyết tốt hơn:

> Trong bốn tuần với các PR cùng loại, việc bổ sung người review dự phòng và thông báo yêu cầu review theo kênh chung sẽ làm **thời gian chờ review trung vị giảm so với kỳ nền**; nếu thời gian chờ không đổi hoặc lỗi sau merge tăng, nhóm sẽ xem lại giải pháp.

Nhóm cũng cần thừa nhận nếu **dữ liệu quá ít** hoặc loại PR giữa các kỳ khác nhau thì chưa đủ để kết luận. “Không có bằng chứng cải thiện” khác “đã chứng minh giải pháp không hiệu quả trong mọi hoàn cảnh”.

## 7. Thiết kế một thử nghiệm nhỏ nhưng đủ học hỏi

### 7.1. Chọn thay đổi nhỏ nhất có thể quan sát

**Smallest useful experiment** không nhất thiết là thay đổi có ít dòng mã nhất. Nó là thử nghiệm **đủ nhỏ để hạn chế rủi ro, đủ rõ để quan sát kết quả và đủ liên quan để kiểm tra giả thuyết**.

Ví dụ để giảm review waiting time, nhóm không nhất thiết phải đổi toàn bộ hệ thống quản lý mã. Có thể:

- Thử người review dự phòng cho một loại PR.
- Giới hạn kích thước PR bằng thỏa thuận chất lượng thay vì ép theo số dòng cứng.
- Mở draft PR sớm cho những thay đổi phụ thuộc nhiều người.
- Dành khoảng thời gian ngắn để xử lý review đang chờ, không làm tăng giờ làm thêm.

Mỗi thử nghiệm nên có **chủ sở hữu, phạm vi, mốc bắt đầu–kết thúc, dữ liệu nền, cách đo và điều kiện dừng/điều chỉnh**.

### 7.2. Ưu tiên tính đảo ngược và tác động hạn chế

| Thử nghiệm | Khả năng hoàn tác | Điều cần kiểm soát |
| --- | --- | --- |
| Thay cách gắn nhãn blocked trên bảng | Thường dễ đảo ngược. | Nhóm phải hiểu cùng chính sách; đo nhất quán. |
| Thêm reviewer dự phòng | Tương đối dễ đổi. | Người dự phòng đủ chuyên môn, không phê duyệt hình thức. |
| Giới hạn WIP ở một bước | Có thể điều chỉnh sau thử. | Không bỏ qua công việc khẩn hoặc làm ẩn WIP. |
| Thử thông báo trạng thái ở nhóm dùng thử | Có thể dùng rollout/flag phù hợp. | Quyền truy cập, đo lường, UX và rollback. |
| Đổi transaction hoặc schema production | Khó hoàn tác, ảnh hưởng dữ liệu. | Kiểm chứng, migration, quyền và phương án khôi phục. |
| Thử trên hệ thống ảnh hưởng tính mạng | Có thể gây hậu quả không chấp nhận. | Không được thay quy trình an toàn bằng thử nghiệm tùy tiện; tuân thủ chuẩn và thẩm quyền chuyên ngành. |

**Thử nghiệm Agile không là giấy phép thử điều nguy hiểm trên người dùng thật.** Những nghĩa vụ bảo mật, dữ liệu, tuân thủ và Definition of Done bắt buộc phải được giữ.

### 7.3. Trước khi thử, thống nhất bảy mục

1. **Vấn đề và đối tượng ảnh hưởng.**
2. **Giả thuyết cơ chế và dự đoán cụ thể.**
3. **Thay đổi được thử, phạm vi và người thực hiện.**
4. **Cách so sánh** với dữ liệu nền, nhóm tương đương hoặc điều kiện ban đầu.
5. **Metric chính** và cách thu/đọc.
6. **Guardrails** cùng điều kiện dừng, quyền quyết định, kế hoạch hoàn tác.
7. **Khi nào và ai** xem bằng chứng để quyết định bước tiếp.

Không cần viết một tài liệu dài cho thay đổi nhỏ. Một thẻ thử nghiệm rõ ràng có thể đủ; thay đổi có rủi ro cao có thể cần thiết kế và phê duyệt chi tiết hơn.

### 7.4. Thử nghiệm không có số đo vẫn có thể học — nếu có bằng chứng rõ

Với vấn đề giao tiếp, nhóm có thể thử một phiên làm rõ yêu cầu ba góc nhìn (*Three Amigos*) rồi quan sát:

- Những câu hỏi nghiệp vụ chưa từng được nêu trước đây có được phát hiện không?
- Những ví dụ nào được bổ sung trước khi code?
- Người tham gia có hiểu cùng kết quả mong muốn không?
- Trong các PBI tiếp theo, có giảm tình huống làm lại do hiểu sai không?

Đây là **bằng chứng định tính và định lượng kết hợp**, không cần giả định mọi điều đều phải được chuyển thành một con số. Tuy nhiên, không nên kết luận giải pháp “thành công” chỉ vì mọi người thích buổi họp nếu không có dấu hiệu giải quyết vấn đề đã chọn.

## 8. Đo lường thử nghiệm: outcome, flow và guardrails

### 8.1. Ba lớp đo khác nhau

| Lớp đo | Câu hỏi | Ví dụ |
| --- | --- | --- |
| **Activity/output** | Chúng ta đã làm gì hoặc tạo ra gì? | Tổ chức hai buổi refinement; thêm bốn integration tests. |
| **Process/flow** | Dòng công việc có tốt hơn không? | Giảm thời gian chờ ở Verify, ít item già, WIP ổn định. |
| **Product outcome** | Người dùng nhận giá trị tốt hơn không? | Học viên tự xác minh được đăng ký, ít phải nhờ support. |

Thử nghiệm giảm chờ review có metric chính là **flow**, nhưng vẫn cần guardrail về chất lượng. Thử nghiệm cải thiện màn hình trạng thái có metric chính là **outcome**, nhưng vẫn cần guardrail về sai lệch dữ liệu và quyền truy cập.

**Đã thêm nhiều test** không tự chứng minh giảm rủi ro. **Đã phát hành tính năng** không tự chứng minh người dùng đạt kết quả. Các lớp đo không thay thế nhau.

### 8.2. Những flow metrics phổ biến

Nếu nhóm dùng Kanban hoặc các phép đo workflow:

- **Work in Progress (WIP):** số item đã bắt đầu nhưng chưa hoàn tất tại một thời điểm.
- **Cycle time:** thời gian từ Started tới Finished của item đã hoàn tất, theo định nghĩa chung.
- **Work item age:** thời gian từ Started tới hiện tại đối với item đang dở.
- **Throughput:** số item Finished trong một khoảng thời gian được xác định.

Ví dụ: một nhóm hoàn tất 12 item trong hai tuần. **Throughput** minh họa là **6 item/tuần** nếu coi hai tuần có cách đo tương đương. Điều này **không nói item có cùng kích thước hoặc giá trị**; không nên dùng số ticket để so năng suất cá nhân hay ép chia giả.

### 8.3. Mốc đo phải được giữ nhất quán

Giả sử trước đây “Finished” nghĩa mã được merge; sau cải tiến, “Finished” nghĩa Increment đã tích hợp, kiểm chứng và đáp ứng DoD. **Cycle time trước/sau không trực tiếp so được** vì điểm kết thúc thay đổi.

Trước khi dùng số đo, nhóm nên ghi:

~~~text
Tên metric: Cycle time cho PBI đã hoàn tất
Started: thời điểm Developers bắt đầu thực hiện PBI
Finished: thời điểm PBI đáp ứng chính sách hoàn tất đã công bố
Đơn vị: ngày lịch (hoặc ngày làm việc; chọn một và giữ nhất quán)
Phạm vi: PBI về luồng đăng ký miễn phí
Loại trừ: chỉ loại trừ theo quy tắc được công bố, không xóa item xấu
Nguồn: lịch sử chuyển trạng thái trên bảng công việc
Chu kỳ xem: theo nhịp retro/flow review của nhóm
~~~

### 8.4. Baseline và cách so sánh

**Baseline** là mức hiện trạng dùng làm tham chiếu, có mô tả **khoảng thời gian, đối tượng, quy tắc và điều kiện**. Nếu chỉ đo sau thay đổi, nhóm có thể tưởng một kết quả là “tốt” mà không biết ban đầu thế nào.

Ví dụ giả định:

| Kỳ | Số PBI đủ điều kiện trong mẫu | Cycle time trung vị | Lỗi sau bàn giao |
| --- | ---: | ---: | ---: |
| Hai tuần trước thử | 10 | 8 ngày | 1 |
| Hai tuần thử chính sách WIP nhỏ | 11 | 6 ngày | 1 |

Có **tín hiệu** thời gian hoàn tất giảm và lỗi quan sát không tăng trong mẫu, nhưng **chưa đủ để quy toàn bộ nguyên nhân cho WIP limit**: loại việc, người tham gia, nghỉ phép, phụ thuộc và ngẫu nhiên có thể khác. Một mẫu nhỏ không chứng minh biện pháp sẽ hiệu quả mãi.

### 8.5. Guardrail metrics: cải thiện một điều mà không gây hại điều khác

| Metric chính muốn cải thiện | Guardrail cần xem |
| --- | --- |
| Giảm thời gian review | Lỗi sau merge, chất lượng review, giờ làm thêm reviewer. |
| Tăng tỷ lệ tự đăng ký | Đăng ký trùng/vượt sức chứa, khiếu nại, quyền riêng tư. |
| Giảm cycle time | DoD, rework, lỗi sau phát hành, mức gián đoạn. |
| Giảm thời gian chạy CI | Lỗi hồi quy bị bỏ sót, flaky test, test bắt buộc vẫn được chạy. |
| Tăng throughput | Mức giá trị thực, WIP, lỗi và sự bền vững của đội. |
| Giảm ticket support | Tỷ lệ hoàn tất tác vụ, mức người dùng bỏ cuộc, severity của lỗi. |

Một thử nghiệm **giảm cycle time nhưng làm tăng sai dữ liệu nghiêm trọng** không thể được gọi là thành công chỉ dựa vào tốc độ.

### 8.6. Đừng dùng một con số để đánh giá con người

Các số như story points, commit, số PR, số bug tìm được hoặc số ticket Done có thể bị tác động bởi cách chia việc và độ phức tạp, không đại diện trực tiếp cho năng lực cá nhân. Khi biến metric thành phần thưởng/trừng phạt, người làm dễ **tối ưu con số thay vì hệ thống**.

Mục tiêu đo lường ở đây là **hiểu luồng, kiểm chứng giả thuyết và cải thiện giá trị**, không phải xếp hạng thành viên.

### 8.7. Little's Law: liên hệ giữa WIP, throughput và thời gian

Trong một hệ thống luồng tương đối ổn định và thỏa các giả định áp dụng, **Little's Law** liên hệ mức công việc dở trung bình, thông lượng và thời gian trong hệ thống trung bình:

\[
\overline{\text{WIP}}\approx
\text{Throughput rate}\times\overline{\text{Cycle time}}.
\]

Ví dụ minh họa, nếu một workflow **ổn định**, trung bình có 6 item đang làm và tốc độ hoàn tất trung bình là 3 item/tuần, thời gian trong workflow trung bình được suy ra xấp xỉ:

\[
\overline{\text{Cycle time}}\approx\frac{6}{3}=2\ \text{tuần}.
\]

Đây **không phải công thức dự báo chắc chắn cho một Sprint ngắn** khi backlog đột ngột thay đổi, cách đếm item khác nhau, WIP/throughput không ổn định hoặc dữ liệu chưa đủ. Cũng không suy từ đây rằng giảm WIP luôn làm cycle time giảm đúng một tỷ lệ; cơ chế thực tế còn chịu ảnh hưởng nghẽn, phụ thuộc và chất lượng.

## 9. Thiết kế so sánh đáng tin cậy: dữ liệu nền, phạm vi và yếu tố gây nhiễu

### 9.1. Trước–sau là điểm khởi đầu, không phải bằng chứng nhân quả tuyệt đối

Một nhóm thử người review dự phòng và thấy review nhanh hơn tuần trước. Kết quả có thể liên quan tới biện pháp, nhưng cũng có thể do:

- Tuần thử chủ yếu có các PR nhỏ.
- Người review chính không còn nghỉ phép.
- Một dự án gấp đã kết thúc, khiến ít PR đổ vào hàng đợi.
- Pipeline được sửa đồng thời, giảm thời gian người review phải chờ.
- Quy tắc tính “ready for review” thay đổi.
- Đội giảm tiêu chuẩn review để chạy nhanh hơn.

Những yếu tố ảnh hưởng đồng thời được gọi chung là **yếu tố gây nhiễu (confounders)** khi chúng có thể làm sai lệch cách diễn giải kết quả.

Vì vậy, báo cáo đúng phải phân biệt:

1. **Điều quan sát được:** thời gian chờ giảm theo cách đo đã thống nhất.
2. **Điều nhóm nghĩ có thể giải thích:** reviewer dự phòng đã giúp giảm hàng đợi.
3. **Điều chưa chắc chắn:** cỡ mẫu, loại việc và những thay đổi khác.
4. **Cần làm tiếp:** giữ thử lâu hơn, so trường hợp tương đương hoặc kiểm tra cơ chế trực tiếp.

**Tương quan không tự chứng minh quan hệ nhân quả.** Tuy nhiên, vì muốn tránh kết luận vội, nhóm cũng không cần đợi một thí nghiệm hoàn hảo cho mọi cải tiến nhỏ, ít rủi ro.

### 9.2. Các cách tạo đối chứng khi phù hợp

| Cách quan sát/thử | Khi hữu ích | Hạn chế |
| --- | --- | --- |
| **So sánh trước–sau** | Workflow nhỏ, thay đổi có khả năng hoàn tác. | Chịu ảnh hưởng xu hướng thời gian, loại công việc, mùa vụ. |
| **Quan sát nhiều thời điểm (run chart)** | Có dữ liệu liên tục, muốn xem xu hướng và biến động. | Chưa loại bỏ mọi nguyên nhân đồng thời. |
| **Nhóm đối chứng tương đương** | Có các nhóm/luồng đủ tương đồng và không gây bất công. | Khác biệt giữa nhóm có thể gây nhiễu. |
| **A/B có phân nhóm phù hợp** | Thử trải nghiệm sản phẩm với lượng người dùng, dữ liệu và quyền cho phép. | Cần thiết kế đo, phân nhóm, chất lượng, đạo đức và kiểm soát tác động. |
| **Phỏng vấn/quan sát trực tiếp** | Muốn hiểu nguyên nhân hành vi hoặc vấn đề chưa đo được. | Mẫu và cách đặt câu hỏi có thể thiên lệch. |
| **Thử nghiệm kỹ thuật tái hiện** | Test lỗi, CI hoặc giới hạn dữ liệu có điều kiện rõ. | Môi trường thử có thể khác production. |

**Không nên A/B test bất kỳ điều gì**: với một số cơ chế bảo mật hoặc kiểm soát tính toàn vẹn, không có chuyện cố tình mở nhóm người dùng “không được bảo vệ” chỉ để tạo đối chứng. Thử nghiệm phải tuân thủ quyền riêng tư, nghĩa vụ an toàn và chính sách sản phẩm.

### 9.3. Khi nào cần cẩn trọng về cỡ mẫu?

Một Sprint nhỏ với 5 PBI có thể cho nhiều insight nhưng ít khả năng khẳng định một thay đổi tạo ra hiệu quả ổn định. Đặc biệt:

- Một item lớn có thể làm trung bình cycle time tăng mạnh.
- Tỷ lệ lỗi hiếm có thể dao động lớn từ 0 sang 1 hoặc 2.
- Một sự cố mạng độc lập có thể làm ngày thử nghiệm khác thường.
- Một khảo sát hài lòng với ba người không đại diện cả tập người dùng.

Nếu quyết định có hậu quả lớn, nhóm cần **mức chứng cứ mạnh hơn**, chuyên gia đánh giá phù hợp, thời gian quan sát đủ và cách kiểm soát rủi ro. Không tự bịa **mức ý nghĩa thống kê, p-value hay cỡ mẫu chuẩn** khi không có thiết kế phân tích đúng.

### 9.4. Chu kỳ thử phải đủ để kết quả xuất hiện

Một thử nghiệm **tích hợp sớm** có thể đo feedback CI trong vài ngày, nhưng số lỗi sau phát hành cần thời gian có người dùng thực. Một cải tiến onboarding học viên có thể cần vài đợt đăng ký để quan sát.

Vì thế, kế hoạch nên xác định:

- **Chỉ số sớm (leading indicator):** tín hiệu sẽ xuất hiện nhanh, như thời gian chờ review hoặc tỷ lệ người dùng tìm thấy trang trạng thái.
- **Chỉ số muộn (lagging indicator):** kết quả cuối cần thời gian, như lỗi hậu phát hành hoặc nhu cầu support.
- **Guardrail theo thời gian thực:** rủi ro phải phản ứng ngay, như đăng ký trùng, lộ dữ liệu hoặc pipeline test bắt buộc bị tắt.

Không giữ thử nghiệm nguy hiểm chỉ để “đủ mẫu”. Nếu guardrail nghiêm trọng bị vi phạm, phải xử lý theo chính sách tại thời điểm đó.

## 10. Thực hiện thử nghiệm và ghi nhận những điều đã xảy ra

### 10.1. Một bản kế hoạch chỉ hữu ích nếu thực tế được ghi lại

Khi bắt đầu thử nghiệm, nên lưu một bản ghi ngắn:

~~~text
Experiment ID: IMP-EXAMPLE-02
Vấn đề: review waiting time cao ở các PR thay đổi API nhỏ
Giả thuyết: reviewer dự phòng giảm thời gian chờ khi reviewer chính bận
Thay đổi: thêm 1 reviewer dự phòng đủ quyền, review theo tiêu chí chung
Phạm vi: PR thay đổi API nội bộ, không bao gồm thay đổi bảo mật cấp cao
Ngày bắt đầu / dự kiến xem: hai tuần thử
Baseline: thời gian từ "ready" tới review có ích ở hai tuần trước
Metric chính: review waiting time theo cùng cách đo
Guardrails: lỗi sau merge, chất lượng review, tải và giờ làm thêm
Owner: đầu mối phối hợp thử nghiệm được nhóm thống nhất
Stop condition: kiểm soát review bắt buộc không đạt hoặc rủi ro tăng
Quyết định sau thử: duy trì / điều chỉnh / hoàn tác / cần quan sát thêm
~~~

Trong thời gian thử, ghi **điều khác kế hoạch**:

- Review dự phòng chỉ hoạt động một tuần vì người được phân công nghỉ phép.
- Một số PR bị dừng do lỗi môi trường, không phải chờ reviewer.
- Tiêu chí chất lượng review thay đổi bởi một chính sách mới.
- Nhóm có một sự cố lớn khiến công việc thông thường bị gián đoạn.

Nếu không ghi các thay đổi này, nhóm có thể so một thử nghiệm trên giấy với dữ liệu của một **thử nghiệm thực tế khác**.

### 10.2. Tránh sửa thước đo sau khi xem kết quả

Một sai lầm thường gặp là trước thử chọn **thời gian chờ review**, nhưng sau khi chỉ số không cải thiện thì chỉ báo cáo **số tin nhắn trong kênh review** vì con số tăng.

Nếu có lý do hợp lệ để thay metric, có thể cập nhật nhưng phải ghi:

- Vì sao metric ban đầu không phù hợp.
- Thời điểm thay đổi định nghĩa.
- Kết quả trước/sau không còn so trực tiếp được ở đâu.
- Dữ liệu nào vẫn có ích cho quyết định tiếp theo.

**Học thêm từ dữ liệu là đúng; chọn lại thước đo sau khi thấy kết quả chỉ để tuyên bố thành công là sai.**

### 10.3. Một bảng dữ liệu nhỏ nhưng có bối cảnh

| Tuần | PBI hoàn tất thuộc phạm vi | Cycle time trung vị | Work item age cao nhất đang dở | Sự kiện đáng chú ý |
| --- | ---: | ---: | ---: | --- |
| Nền 1 | 6 | 8 ngày | 13 ngày | Môi trường kiểm thử gián đoạn một lần. |
| Nền 2 | 5 | 9 ngày | 15 ngày | Một PBI phụ thuộc API ngoài nhóm. |
| Thử 1 | 6 | 7 ngày | 11 ngày | Giảm WIP; một người nghỉ hai ngày. |
| Thử 2 | 7 | 6 ngày | 9 ngày | Tích hợp sớm, không có sự cố môi trường lớn. |

Đây là **dữ liệu minh họa**. Nó giúp thảo luận về xu hướng, nhưng chưa đủ để nói “giảm WIP chắc chắn tạo giảm 3 ngày”. Phải xem **độ tương đồng giữa các PBI**, chất lượng và thay đổi điều kiện theo thời gian.

## 11. Học từ kết quả: giữ, thích ứng, hoàn tác hoặc thử tiếp

### 11.1. Bốn hướng quyết định hữu ích

| Kết quả | Quyết định có thể phù hợp | Vì sao |
| --- | --- | --- |
| Tín hiệu chính cải thiện, guardrails đạt và dữ liệu đủ đáng tin trong phạm vi | **Duy trì / chuẩn hóa có theo dõi** | Biện pháp có vẻ hữu ích; vẫn cần kiểm tra sau khi mở rộng. |
| Có lợi ích cục bộ nhưng rủi ro/tác dụng phụ chưa đạt | **Điều chỉnh hoặc hạn chế phạm vi** | Không đánh đổi chất lượng bắt buộc để giữ một chỉ số tốt. |
| Không thấy lợi ích và chi phí/tác động phụ không hợp lý | **Hoàn tác / chọn giải pháp khác** | Dữ liệu không ủng hộ tiếp tục như hiện tại. |
| Dữ liệu chưa đủ hoặc thử nghiệm bị gián đoạn | **Thu thêm bằng chứng / thiết kế thử khác** | Chưa thể kết luận tác dụng hay không tác dụng. |

Đây **không phải thuật toán tự động**. Với vấn đề an toàn và nghĩa vụ pháp lý, quyết định phải tuân theo thẩm quyền và quy trình chuyên môn. Một vi phạm nghiêm trọng có thể yêu cầu dừng ngay, dù metric chính đẹp.

### 11.2. Mẫu kết luận thử nghiệm

~~~text
Kết quả quan sát:
  [giá trị đo, mẫu, thời gian, định nghĩa và phản hồi định tính]

So với giả thuyết:
  [đúng phần nào, sai phần nào, chưa biết điều gì]

Yếu tố gây nhiễu hoặc giới hạn:
  [loại việc, thay đổi khác, cỡ mẫu, cách đo, dữ liệu thiếu]

Guardrails:
  [chất lượng/riêng tư/workload/rủi ro có đạt không]

Quyết định:
  [giữ / điều chỉnh / hoàn tác / cần thử tiếp]

Lý do:
  [bằng chứng liên quan, không diễn giải quá mức]

Hành động tiếp theo:
  [owner, việc cụ thể, khi nào kiểm tra lại]
~~~

### 11.3. Thất bại trong thử nghiệm không đồng nghĩa thất bại của nhóm

Giả sử nhóm tin rằng thêm một buổi họp hằng ngày giúp giảm chờ. Sau hai tuần, chờ review không thay đổi nhưng tổng thời gian gián đoạn tăng. Đó vẫn có thể là **một thử nghiệm có giá trị**, vì nhóm đã bác bỏ một giả thuyết và tránh kéo dài một hoạt động gây lãng phí.

Điều cần khuyến khích là:

- Thẳng thắn ghi điều quan sát được.
- Không thay số liệu hoặc đổi tiêu chí để “có thành tích”.
- Học được cơ chế nào không đúng.
- Đề xuất thử nghiệm kế tiếp hẹp hơn.
- Gỡ bỏ hoạt động không hữu ích.

Tuy nhiên, **thất bại có thể chấp nhận trong một thử nghiệm được kiểm soát** không đồng nghĩa được thử nghiệm bất cẩn trên người dùng hoặc bỏ qua kiểm soát bắt buộc.

### 11.4. Chuẩn hóa không phải đóng băng quy trình

Khi một thay đổi có bằng chứng hữu ích, nhóm có thể cập nhật:

- **Working agreement** về thời gian review và người hỗ trợ dự phòng.
- **Definition of Workflow** và WIP policies của Kanban.
- **Definition of Done** hoặc kiểm thử cần thiết, nếu tuân theo trách nhiệm và chuẩn tổ chức.
- **Runbook/CI** hoặc mẫu ticket giúp phát hiện lỗi sớm.
- **Backlog/refinement policy** cho những rủi ro thường gặp.

Sau đó cần quan sát liệu thay đổi còn hiệu quả khi **loại việc, con người, rủi ro hoặc quy mô** thay đổi. Cải tiến liên tục không phải tạo một quy trình vĩnh viễn không còn được xem lại.

## 12. Tình huống xuyên suốt A: cải thiện trải nghiệm sau timeout đăng ký

### 12.1. Vấn đề ban đầu

Một đội phát triển nền tảng học trực tuyến đã tạo luồng đăng ký khóa miễn phí. Sau release, support ghi nhận nhiều yêu cầu **“Tôi đã đăng ký được chưa?”**. Nhóm nghi người học gặp timeout rồi không biết trạng thái thực.

Đây là **tình huống và số liệu giả định phục vụ học tập**, không phải dữ liệu sản phẩm có thật.

Trong một kỳ nền:

- Có **2.000 học viên** thực hiện ít nhất một thao tác đăng ký thuộc phạm vi đo.
- Có **80 ticket** về trạng thái đăng ký, theo quy tắc không đếm trùng ticket cùng vụ việc.
- Trong một số phiên quan sát người dùng, học viên thấy thông báo lỗi mạng và thử gửi lại.
- Hệ thống có test cho happy path nhưng chưa có kiểm chứng toàn diện về phản hồi bị mất sau khi DB commit.

Tỷ lệ ticket mô tả ban đầu là:

\[
\frac{80}{2.000}\times100\%=4\%.
\]

Đây là một **tỷ lệ ticket trên tập học viên thực hiện thao tác**, không nhất thiết là xác suất một học viên gặp lỗi: một học viên có thể tạo nhiều ticket, kênh hỗ trợ có thể không ghi nhận mọi trường hợp và định nghĩa mẫu phải được giữ nhất quán.

### 12.2. Mô tả khoảng cách cần cải thiện

> Học viên cần biết chính xác trạng thái đăng ký khi kết nối bị lỗi. Hiện tại, nhiều người phải nhờ support hoặc thử lại không có căn cứ. Chúng ta muốn nhiều học viên **tự xác minh trạng thái thật**, giảm nhu cầu hỗ trợ, đồng thời **không tạo đăng ký trùng, không lộ dữ liệu hoặc thông báo sai**.

Phần **không tạo đăng ký trùng/không lộ dữ liệu** là giới hạn chất lượng phải đạt, không phải số đo tùy chọn được hy sinh để tăng tỷ lệ tự phục vụ.

### 12.3. Quan sát và giả thuyết

Nhóm thu bằng chứng qua support, kiểm tra UI và log có quyền truy cập hợp lệ:

1. Người dùng thấy “Không thành công” khi client timeout, dù request có thể đã commit.
2. UI chưa có bước tra trạng thái thật trước khi đề nghị thử lại.
3. Nhóm chưa phân biệt rõ trạng thái **chưa lưu** với **không nhận được phản hồi**.
4. Một số ticket có cùng triệu chứng, nhưng chưa đủ để nói mọi trường hợp đều do timeout.

Giả thuyết:

> Nếu bổ sung **cách xem trạng thái đăng ký thực sau timeout** và thay thông báo mơ hồ bằng chỉ dẫn an toàn, học viên sẽ xác minh trạng thái mà không gửi yêu cầu hỗ trợ; tỷ lệ ticket về trạng thái sẽ giảm so với nền trong những nhóm người dùng tương đương, **không tăng** lỗi đăng ký trùng hoặc sai quyền.

### 12.4. Thiết kế thử nghiệm

| Thành phần | Kế hoạch minh họa |
| --- | --- |
| **Đối tượng** | Một nhóm học viên thử nghiệm đủ điều kiện, được chọn theo cơ chế phù hợp và có quyền riêng tư được bảo vệ. |
| **Thay đổi** | UI phân biệt timeout với kết quả thất bại chắc chắn, cung cấp chức năng tra trạng thái thật có phân quyền. |
| **Kiểm chứng kỹ thuật** | Test request lặp, DB transaction, authorization, các trường hợp lỗi mạng. |
| **Metric chính** | Tỷ lệ ticket về trạng thái trên số học viên thao tác thuộc phạm vi, cùng quy tắc tính. |
| **Tín hiệu bổ sung** | Khả năng tự xác minh, người dùng hiểu thông báo, số lần retry. |
| **Guardrails** | Không có dữ liệu đăng ký trùng/vượt sức chứa do thử nghiệm, không lộ dữ liệu, không tăng sự cố nghiêm trọng. |
| **Nhịp xem** | Theo các đợt đăng ký với lượng người dùng phù hợp, không ép kết luận chỉ sau vài thao tác. |
| **Điều kiện dừng** | Bất kỳ dấu hiệu nghiêm trọng nào về sai dữ liệu hoặc quyền truy cập phải kích hoạt xử lý theo chính sách. |

Trước rollout, nhóm cần đáp ứng **DoD và các điều kiện phát hành**. Không dùng người dùng production làm đối tượng kiểm thử cho một cơ chế ghi dữ liệu chưa an toàn.

### 12.5. Ví dụ chấp nhận sản phẩm

~~~gherkin
Feature: Tự tra trạng thái đăng ký sau khi mất kết nối

  Scenario: Đăng ký đã được lưu nhưng phản hồi mạng bị mất
    Given học viên A đã đăng nhập
    And có một đăng ký hiệu lực của A cho khóa X
    And phản hồi của thao tác đăng ký trước không tới trình duyệt
    When A kiểm tra trạng thái đăng ký khóa X của mình
    Then A thấy trạng thái đã được xác nhận từ hệ thống
    And thao tác kiểm tra không tạo bản ghi đăng ký mới

  Scenario: Chưa có đăng ký hiệu lực
    Given A chưa có đăng ký hiệu lực cho khóa X
    When A kiểm tra trạng thái đăng ký của mình
    Then A không nhận thông báo thành công sai
    And hệ thống không tự tạo đăng ký mới chỉ vì thao tác tra cứu

  Scenario: Người khác cố đọc trạng thái riêng
    Given B không có quyền đọc đăng ký của A
    When B yêu cầu tra cứu đăng ký của A
    Then hệ thống từ chối truy cập

  Scenario: Gửi lại yêu cầu sau timeout
    Given yêu cầu đăng ký ban đầu của A đã được lưu hợp lệ
    When A gửi lại yêu cầu đăng ký cùng khóa theo chính sách hệ thống
    Then không tạo đăng ký hiệu lực trùng cho A
    And A biết trạng thái cuối chính xác
~~~

Gherkin mô tả **hành vi cần kiểm chứng**, không tự là test tự động. Developers cần kết nối kịch bản với test, dữ liệu, môi trường và thiết kế idempotency/authorization phù hợp.

### 12.6. Quan sát kết quả và tránh suy diễn

Giả sử sau một kỳ thử có **2.100 học viên** thực hiện thao tác trong phạm vi và **60 ticket** cùng chủ đề:

\[
\frac{60}{2.100}\times100\%\approx2{,}86\%.
\]

Mức quan sát giảm từ khoảng **4% xuống 2,86%**, tức **1,14 điểm phần trăm**. Đây là **tín hiệu tốt để điều tra thêm**, không phải chứng minh tuyệt đối thay đổi UI đã gây ra toàn bộ mức giảm. Nhóm cần xem:

- Hai kỳ có cùng cách ghi ticket và cách đếm học viên không?
- Các khóa có số chỗ, mạng, tải và hành vi người dùng tương đương không?
- Có sự cố hoặc thay đổi API khác trong thời gian thử không?
- Những người không mở ticket có thực sự tự hoàn tất hay đã bỏ cuộc?
- Guardrails về dữ liệu trùng và phân quyền đã được xác minh chưa?
- Tác động lên support và độ trễ hệ thống có chấp nhận được không?

Nếu bằng chứng đủ đáng tin trong phạm vi, nhóm có thể **duy trì và mở rộng có kiểm soát**, đồng thời giữ theo dõi sau rollout. Nếu vẫn còn nhiều trường hợp không rõ trạng thái, có thể thử cải thiện thông báo, luồng tra cứu hoặc cơ chế xử lý backend.

### 12.7. Bài học quan trọng

Thay đổi mang lại lợi ích không chỉ ở việc thêm một màn hình. Nhóm phải cải thiện **khả năng tra trạng thái thật, test lỗi mạng, tài liệu hỗ trợ, quan sát dữ liệu và cách nhận phản hồi**. Đó là cải tiến vòng giá trị, không chỉ một output giao diện.

## 13. Tình huống B: giảm WIP để tăng khả năng hoàn tất trong Kanban

### 13.1. Quan sát

Một nhóm phát triển có bốn cột **Ready → Developing → Verify → Done**. Họ thấy nhiều thẻ đã bắt đầu nhưng Verify luôn nghẽn. Thành viên lại tiếp tục kéo thẻ mới vì “không muốn bị rảnh”.

Trong ba tuần, các dấu hiệu giả định:

- WIP tại bước Developing + Verify thường cao.
- Item bị chặn không được ghi nguyên nhân.
- Những item lâu nhất phải chờ môi trường kiểm thử hoặc người review.
- Throughput tăng không tương xứng với số item đang mở.

**Giả thuyết:** nếu giới hạn công việc dở và ưu tiên hỗ trợ hoàn tất item đang chờ, cycle time/work item age sẽ cải thiện vì hàng đợi và chuyển ngữ cảnh giảm.

### 13.2. Thiết kế thử

1. Định nghĩa rõ **Started** tại lúc item chuyển sang Developing và **Finished** tại khi đáp ứng điều kiện Done.
2. Thử WIP limit **3** cho vùng Developing + Verify trong một thời gian có thể quan sát, thay vì mức WIP cao trước đó.
3. Khi vùng đầy, thành viên không tự kéo task mới; trước tiên xem có thể giúp kiểm thử, review hay tháo blocker không.
4. Dùng tín hiệu blocked, work item age và nguyên nhân phụ thuộc để ưu tiên hỗ trợ.
5. Giữ các điều kiện Done, kiểm thử và chất lượng; không chuyển thẻ Done khi chưa đạt.
6. Theo dõi throughput, cycle time, tuổi item cũ, lỗi và tải công việc; xem lại sau thử.

**WIP limit = 3** chỉ là giá trị minh họa, không phải tiêu chuẩn Kanban cho mọi nhóm. Mức hợp lý phụ thuộc năng lực, cách chia việc và workflow; không nên áp cùng một số cho mọi dịch vụ.

### 13.3. Kết quả giả định

| Kỳ quan sát | Item Finished | Cycle time trung vị | Work item age lớn nhất còn dở | Lỗi sau phát hành |
| --- | ---: | ---: | ---: | ---: |
| Nền (3 tuần) | 18 | 9 ngày | 17 ngày | 2 |
| Thử (3 tuần) | 19 | 6 ngày | 11 ngày | 2 |

Kết quả có vẻ cho thấy luồng **hoàn tất đều hơn**, nhưng còn nhiều câu hỏi:

- Tập item có tương đương kích thước/rủi ro không?
- Có item rất lớn chưa Finished nên không xuất hiện trong cycle time trung vị không?
- WIP thực tế có thật sự được giữ trong giới hạn không?
- Công việc khẩn có chen ngang và được đếm minh bạch không?
- Dữ liệu ba tuần có đủ để dự báo ổn định không?
- Có điều kiện chất lượng nào bị bỏ qua để tăng throughput không?

**Work item age của những item còn dở** giúp tránh lỗi nhìn mỗi item đã Finished mà bỏ quên hàng đợi cũ. Nếu một item tồn đọng vẫn tăng tuổi, nhóm cần giải quyết blocker thay vì chỉ nhắm trung vị đẹp.

### 13.4. Khi giả thuyết không đúng

Nếu giới hạn WIP nhưng item vẫn chờ do **môi trường tích hợp liên tục hỏng**, giảm WIP đơn thuần có thể làm nhóm ít việc đang mở hơn mà không tăng tốc hoàn tất. Khi đó thử nghiệm tiếp theo nên hướng vào **ổn định môi trường/test và tháo rào cản phối hợp**, không tăng WIP tùy ý hoặc kết luận mọi người lười.

Kanban hữu ích vì làm tình trạng luồng **hiện ra rõ** và cho nhóm kiểm chứng chính sách một cách tiến hóa.

## 14. Tình huống C: cải thiện feedback CI mà không làm yếu kiểm thử

### 14.1. Quan sát

Một nhóm dùng nhánh Git ngắn và CI, nhưng mỗi lần push phải chờ 35 phút mới biết kết quả. Developers thường tạo nhiều thay đổi mới trong lúc đợi; tới khi test đỏ, họ đã chuyển ngữ cảnh.

Các giả thuyết có thể gồm:

- Quá nhiều test chậm chạy tuần tự.
- Môi trường được tạo lại mỗi lần dù có thể tối ưu an toàn.
- Một số integration tests phụ thuộc dữ liệu chung, gây flaky.
- CI runner thường xếp hàng trước khi bắt đầu.

**Không nên bắt đầu bằng kết luận “hãy bỏ integration tests”** vì có thể làm mainline xanh nhanh nhưng bỏ sót lỗi dữ liệu.

### 14.2. Thử nghiệm nhỏ với guardrails

Một giả thuyết:

> Nếu chạy các unit tests nhanh và kiểm tra tĩnh sớm, đồng thời cho các nhóm integration tests độc lập chạy song song với dữ liệu cách ly, nhóm sẽ nhận phản hồi cần thiết nhanh hơn **mà vẫn chạy đầy đủ các phép kiểm tra bắt buộc trước merge**.

Kế hoạch:

| Mục | Nội dung |
| --- | --- |
| **Thay đổi** | Phân tầng test, chạy song song những job độc lập, cải thiện setup dữ liệu. |
| **Phạm vi** | CI của module đăng ký, không cấp thêm quyền production cho runner. |
| **Metric chính** | Thời gian từ push tới kết quả kiểm tra cần thiết. |
| **Metric bổ sung** | Thời gian runner chờ, tỷ lệ flaky, tỷ lệ mainline đỏ, review wait. |
| **Guardrails** | Không bỏ test cạnh tranh/idempotency/quyền; không tăng lỗi sau merge. |
| **Bằng chứng** | Kết quả nhiều lần chạy trên PR và bản tích hợp, kiểm tra đủ các job. |

Ví dụ dữ liệu minh họa: thời gian chạy kiểm tra bắt buộc trung vị giảm **35 → 18 phút**. Đây là cải thiện về feedback time **nếu cùng tập kiểm tra và cùng điều kiện đo**; chưa chứng minh toàn bộ chất lượng sản phẩm tốt hơn.

### 14.3. Nếu phải tối ưu thêm, nên thử cái gì?

- Xem phần thời gian **chờ runner** so với **thời gian chạy test**.
- Giảm việc tải lại phụ thuộc với cache an toàn và kiểm soát tính tái lập.
- Chia test theo loại rủi ro và mức phản hồi cần thiết, không xóa test quan trọng.
- Sửa flaky test theo nguyên nhân, không rerun tới khi xanh.
- Cải thiện contract tests và test dữ liệu có khả năng phát hiện xung đột sớm.
- Xem khả năng sử dụng merge queue hoặc kiểm tra bản tích hợp dự kiến nếu có nhiều PR đồng thời.

Nhóm nên đánh giá **cả tốc độ lẫn độ tin cậy của CI**. Một pipeline báo kết quả rất nhanh nhưng bỏ qua lỗi nghiêm trọng làm tăng chi phí sửa sau phát hành.

## 15. Lean, Kaizen, Toyota Kata và A3 giúp vòng cải tiến sâu hơn

### 15.1. Kaizen không đồng nghĩa tổ chức thật nhiều buổi họp

Trong tư duy Lean, **Kaizen** nhấn mạnh cải tiến liên tục qua việc hiểu công việc thực, nhìn thấy vấn đề và thay đổi có học hỏi. Nó gắn với **tôn trọng con người**: người trực tiếp làm, người dùng, support và vận hành phải có khả năng nêu vấn đề và tham gia giải quyết.

Một buổi retrospective tạo 25 đề xuất nhưng không có owner, thử nghiệm hoặc kiểm tra tác dụng **chưa tạo được vòng cải tiến**. Trái lại, một thay đổi nhỏ giúp giảm lỗi và được đo đúng có thể rất có giá trị.

### 15.2. Improvement Kata: luyện thói quen đi từ hiện trạng tới target condition

Một cách diễn giải thường dùng của **Toyota Kata/Improvement Kata**:

1. Hiểu **hướng đi/thách thức** về giá trị.
2. Nắm **hiện trạng** bằng quan sát.
3. Xác định **trạng thái mục tiêu kế tiếp (target condition)** có thể đạt.
4. Làm các **bước thử nghiệm** để vượt những trở ngại chưa hiểu.
5. So điều dự đoán với điều thực sự xảy ra và học tiếp.

Ví dụ:

| Thành phần Kata | Nhóm đăng ký khóa học |
| --- | --- |
| **Hướng đi** | Học viên tự đăng ký đáng tin cậy, không phải nhờ support. |
| **Hiện trạng** | Nhiều ticket về timeout và trạng thái không rõ. |
| **Trạng thái mục tiêu gần** | Người dùng tự kiểm tra được trạng thái sau lỗi mạng trong phạm vi thử. |
| **Trở ngại** | API chưa có cách tra trạng thái an toàn, test retry thiếu. |
| **Bước thử kế tiếp** | Xây lát cắt tra cứu có kiểm thử phân quyền/idempotency và nhận phản hồi. |
| **Điều học được** | So tỷ lệ hoàn tất, ticket và guardrails với dự đoán. |

**Target condition** thường gần và cụ thể hơn tầm nhìn dài hạn. Sau khi đạt hoặc học được điều mới, nhóm chọn trạng thái tiếp theo thay vì lập một kế hoạch bất biến cho mọi chi tiết.

### 15.3. Coaching Kata: câu hỏi giúp đội tự giải quyết

Một người hỗ trợ/leader có thể hỏi:

- Target condition đang hướng tới là gì?
- Hiện trạng thực tế mà chúng ta thấy là gì?
- Trở ngại nào đang được giải quyết trước tiên?
- Bước thử nhỏ kế tiếp là gì?
- Chúng ta dự đoán điều gì sẽ xảy ra?
- Khi nào có thể xem kết quả thực?
- Điều đã xảy ra khác dự đoán ở đâu?

Coaching không có nghĩa lãnh đạo rút hết trách nhiệm. Người có thẩm quyền vẫn phải **gỡ trở ngại liên nhóm, cấp quyền hợp lệ, giữ tiêu chuẩn chất lượng và hỗ trợ năng lực**.

### 15.4. A3: một tờ giấy để tư duy có cấu trúc

**A3 problem solving** có thể tóm tắt:

| Mục | Nội dung |
| --- | --- |
| Bối cảnh và giá trị | Tại sao vấn đề đáng giải quyết? |
| Hiện trạng | Dữ liệu, quan sát và giới hạn. |
| Khoảng cách | Kết quả hiện tại khác target condition thế nào? |
| Nguyên nhân khả dĩ | Những giả thuyết và bằng chứng cần kiểm tra. |
| Đối sách/thử nghiệm | Thay đổi nhỏ nhất có thể kiểm chứng. |
| Kế hoạch | Phạm vi, owner, mốc, metric, guardrails. |
| Theo dõi | Kết quả và quyết định tiếp. |

**A3 không phải một biểu mẫu phải viết dài hoặc xin ký cho mọi thay đổi**. Giá trị nằm ở **lập luận minh bạch, học hỏi chung và việc kiểm chứng quyết định**.

## 16. Scrum: biến Sprint Review và Retrospective thành vòng học hỏi

### 16.1. Hai loại câu hỏi ở hai sự kiện khác nhau

Trong Scrum, kiểm tra–thích ứng xảy ra liên tục, nhưng **Sprint Review** và **Sprint Retrospective** nhấn mạnh những góc nhìn khác nhau:

| Sự kiện | Trọng tâm | Tín hiệu có thể dùng | Hành động tiếp |
| --- | --- | --- | --- |
| **Sprint Review** | Kiểm tra kết quả Sprint, tiến độ hướng Product Goal và bối cảnh sản phẩm; cộng tác xác định hướng tiếp theo. | Increment đã đạt DoD, phản hồi người dùng, biến động thị trường, dữ liệu sử dụng. | Product Backlog có thể được điều chỉnh để tối đa hóa giá trị. |
| **Sprint Retrospective** | Lập kế hoạch tăng chất lượng và hiệu quả của Scrum Team. | Luồng công việc, lỗi, DoD, cộng tác, sự cố, công cụ, quan hệ và quy trình. | Chọn cải tiến cách làm có thể kiểm chứng. |

Đây không phải hai phòng họp biệt lập. Một phản hồi ở Sprint Review có thể làm nhóm thấy cần cải thiện cách kiểm thử; một trở ngại ở Retro có thể khiến Product Owner cân nhắc đầu tư vào khả năng quan sát. Mỗi quyết định vẫn cần **người chịu trách nhiệm và bằng chứng**.

### 16.2. Một Sprint Retrospective tạo thử nghiệm ra sao?

Ví dụ:

- **Quan sát:** ba PBI không đạt DoD vì kiểm thử tích hợp bị dồn cuối Sprint.
- **Vấn đề:** thiếu khả năng có Increment tích hợp sớm.
- **Giả thuyết:** chia PBI thành lát cắt dọc và xác định test từ refinement giúp giảm lỗi tích hợp muộn.
- **Thử nghiệm:** trong Sprint kế tiếp, áp dụng cho hai PBI phù hợp, có người kiểm thử và Developers cùng làm rõ.
- **Metric:** thời điểm bản tích hợp đầu tiên chạy được, work item age của PBI, lỗi phát hiện ở giai đoạn nào.
- **Guardrail:** không giảm DoD, không bỏ test bảo mật/tính nhất quán.
- **Kiểm tra:** xem dữ liệu và phản hồi ở Retro tiếp theo, không chỉ hỏi “mọi người thấy thế nào”.

Không phải mọi cải tiến cần đợi Sprint mới bắt đầu. Nếu pipeline chính bị đỏ, nhóm phải xử lý theo mức rủi ro ngay, không chờ tới Retrospective. Một số cải tiến có thể diễn ra **ngay trong Sprint** miễn không phá mục tiêu/điều kiện chất lượng.

### 16.3. Daily Scrum là cơ hội điều chỉnh kế hoạch gần mục tiêu

Daily Scrum là sự kiện của Developers để **kiểm tra tiến độ hướng Sprint Goal và điều chỉnh Sprint Backlog**, không phải buổi nộp báo cáo trạng thái cho quản lý. Trong quá trình này, Developers có thể nhận thấy:

- Hạng mục nào đang bị chặn.
- Một giả định kỹ thuật vừa sai.
- Cần phối hợp sớm với người hiểu nghiệp vụ.
- Cần tập trung giúp hoàn tất Increment trước khi kéo việc mới.

Việc rút kinh nghiệm và thử điều chỉnh nhỏ có thể bắt đầu ngay. Không nhất thiết xây một chương trình đo lường riêng cho mọi quyết định thường ngày, nhưng **vấn đề lặp lại đáng được ghi thành thử nghiệm có cấu trúc**.

### 16.4. Product Owner, Developers và Scrum Master hỗ trợ vòng cải tiến

- **Product Owner:** nêu mục tiêu giá trị, làm rõ outcome, quản lý thứ tự Product Backlog và quyết định các đánh đổi sản phẩm trong phạm vi quyền.
- **Developers:** tạo Increment đạt DoD, thực hiện cải tiến kỹ thuật và phối hợp điều chỉnh Sprint Backlog để đạt Sprint Goal.
- **Scrum Master:** phục vụ Scrum Team/tổ chức trong việc áp dụng Scrum hiệu quả, giúp gỡ trở ngại, huấn luyện thực hành kiểm tra–thích ứng.

Một Scrum Team **tự quản lý** cách biến ý tưởng thành giá trị. Thử nghiệm cải tiến không được dùng để thêm một “người phê duyệt Retrospective” hay biến Scrum Master thành người giao task cho Developers.

### 16.5. Cải tiến không được thay DoD tùy tiện

Giả sử nhóm muốn tăng throughput bằng cách chuyển “Done” từ **phần mềm tích hợp, kiểm tra đạt** thành **code đã merge**. Chỉ số có thể tăng nhưng không chứng minh hiệu quả tốt hơn; nó chỉ **thay đổi định nghĩa đo** và hạ chuẩn nếu các điều kiện trước là bắt buộc.

Đúng hơn là:

1. Giữ ranh giới Done minh bạch và đáp ứng các chuẩn tổ chức.
2. Tìm nguyên nhân khiến test/verification chậm.
3. Tối ưu quá trình với kiểm chứng tương đương.
4. Nếu có thay đổi chính sách DoD hợp lệ, công bố sự thay đổi và không so sánh số liệu cũ/mới như cùng một mốc.

## 17. Kanban: cải tiến tiến hóa dựa trên luồng công việc

### 17.1. Hình dung workflow và thắt nút

Kanban giúp thấy được **các hạng mục đã bắt đầu, đang chờ và đã hoàn tất**. Một workflow minh họa:

~~~mermaid
flowchart LR
    A["Ready"] --> B["Developing"]
    B --> C["Review / CI"]
    C --> D["Verify"]
    D --> E["Done"]
    C -. "Rework" .-> B
    D -. "Rework" .-> B
~~~

Điều quan trọng không phải phải dùng đúng các cột trên, mà là nhóm có **Definition of Workflow (DoW)**: loại item, ranh giới bắt đầu/kết thúc, trạng thái, cách kiểm soát WIP và các chính sách chuyển trạng thái rõ ràng.

Nếu một thẻ đang bị chặn, nó vẫn cần được nhìn thấy. Xóa thẻ khỏi bảng hoặc tạm “đóng” nó để chỉ số WIP đẹp lên khiến nhóm không còn biết nguyên nhân hàng đợi.

### 17.2. Quan sát một item già hơn kỳ vọng

Ví dụ:

- SLE của nhóm dựa trên lịch sử cho một loại PBI là “phần lớn item tương tự hoàn tất trong một khoảng thời gian nhất định”.
- Một PBI đang dở có **work item age** cao bất thường.
- Nhóm xem bước nào đang chờ, điều kiện nào chưa đạt và ai có thể hỗ trợ.

**SLE (Service Level Expectation)** là kỳ vọng có tính xác suất cho thời gian hoàn tất theo định nghĩa và dữ liệu phù hợp, **không tự là cam kết SLA hợp đồng**. Không nên dùng SLE như thời hạn cứng để buộc thành viên bỏ test hoặc đánh dấu Done.

### 17.3. Kết hợp WIP limit với giả thuyết

Một lỗi phổ biến là đặt WIP limit nhưng không nói rõ **vì sao** hoặc làm gì khi đạt giới hạn. Nếu muốn thử giảm WIP để giảm cycle time, nhóm cần:

1. Xác định hàng đợi đang ảnh hưởng tới phần nào của workflow.
2. Thống nhất hành vi khi WIP đầy: giúp hoàn tất, tháo blocker, sửa test, review.
3. Công bố cách xử lý ngoại lệ khẩn cấp và quy tắc đếm WIP.
4. Thu baseline và ghi thay đổi chính sách.
5. Quan sát work item age, cycle time, throughput, lỗi và tải công việc.
6. Quyết định giữ/sửa WIP limit dựa trên kết quả.

**Giảm WIP chỉ là đối sách**, không phải mục tiêu sản phẩm. Nếu bottleneck thực là dịch vụ ngoài nhóm không sẵn sàng, cần can thiệp vào phụ thuộc thay vì chỉ ép số item trên bảng.

### 17.4. Sự khác nhau giữa cải tiến hằng ngày và thử nghiệm chính thức

| Tình huống | Hành động hợp lý |
| --- | --- |
| Một item blocked do thiếu quyền đọc log | Xin quyền hợp lệ hoặc người có quyền hỗ trợ ngay; ghi lại blocker nếu cần. |
| Nhiều item bị chặn bởi cùng một bước review | Tạo giả thuyết và thử chính sách review mới có số đo. |
| Dữ liệu cho thấy WIP tăng và cycle time kéo dài | Xem workflow, thử giới hạn WIP/giảm batch size và quan sát. |
| Một phản hồi người dùng cho thấy tính năng sai nghiệp vụ | Phân loại defect/incident, xử lý theo rủi ro và PO tham gia khi cần. |
| Một thay đổi chính sách được kiểm chứng hiệu quả | Cập nhật explicit policies và tiếp tục theo dõi. |

Cải tiến liên tục không yêu cầu biến **mọi quyết định nhỏ thành thí nghiệm A/B**. Nên tăng độ chính thức của thử nghiệm theo mức rủi ro và độ khó xác định tác dụng.

## 18. XP và thực hành kỹ thuật: giảm độ trễ phản hồi để học nhanh hơn

### 18.1. Test-Driven Development là một vòng phản hồi ở cấp mã

Trong **Test-Driven Development (TDD)**, vòng **Red → Green → Refactor** tạo một thử nghiệm kỹ thuật liên tục:

1. Viết một test thể hiện hành vi cần thiết và xác nhận nó thất bại vì lý do mong đợi.
2. Viết mã để đáp ứng hành vi tối thiểu.
3. Cải thiện thiết kế trong khi test bảo vệ hành vi.

Đây không phải bằng chứng duy nhất về chất lượng hệ thống. Unit test xanh chưa chứng minh transaction đồng thời hoặc quyền truy cập đúng khi tích hợp. Với các rủi ro đó cần **integration tests, contract tests và những kiểm chứng khác**.

### 18.2. CI và nhánh mã ngắn giảm khoảng cách giữa quyết định và phản hồi

Nếu nhóm giữ nhánh riêng nhiều tuần, họ có thể không biết hai phần mềm mâu thuẫn cho tới khi ghép. **Continuous Integration** và thay đổi nhỏ giúp đưa phản hồi tích hợp tới sớm:

| Vấn đề quan sát | Giả thuyết kỹ thuật | Thử nghiệm |
| --- | --- | --- |
| Lỗi hợp đồng chỉ lộ cuối Sprint | Ghép API/consumer muộn. | PR nhỏ, contract tests và tích hợp thường xuyên. |
| Review chờ lâu và PR khó đọc | Thay đổi quá lớn, ít người hiểu. | Chia PR hẹp, mô tả rủi ro, pairing khi phù hợp. |
| Mainline đỏ lâu | Không có policy phản ứng khi kiểm tra thất bại. | Quy ước ưu tiên sửa/revert an toàn, ghi và đo thời gian khôi phục. |
| Test CI không đáng tin | Dữ liệu dùng chung, phụ thuộc thời gian hoặc môi trường không ổn định. | Cách ly dữ liệu, sửa đồng bộ và làm rõ tính tái hiện. |

**Thử nghiệm tối ưu kỹ thuật cũng cần guardrails.** Không giảm thời gian pipeline bằng cách vô hiệu hóa test bắt buộc hay bỏ qua quyền truy cập.

### 18.3. Pairing, refactoring và chia sẻ tri thức

Một thử nghiệm pairing cho phần thay đổi phức tạp có thể nhằm:

- Giảm số vòng review do thiếu bối cảnh.
- Phát hiện điều kiện biên sớm.
- Chia sẻ kiến thức về thành phần phụ thuộc.
- Giảm rủi ro khi chỉ một người biết xử lý sự cố.

Để kiểm chứng, có thể xem số lần làm lại, thời gian chờ, lỗi sau merge và phản hồi từ người tham gia. Không nên đánh giá pairing chỉ bằng **số dòng mã mỗi người tạo ra**; cũng không nên ép mọi thay đổi phải pair nếu chi phí vượt lợi ích.

### 18.4. Phân biệt thử nghiệm kỹ thuật với hạ chuẩn chất lượng

Một cải tiến kỹ thuật tốt có thể:

- Cắt thời gian chờ nhờ test chạy song song **mà giữ phạm vi kiểm chứng**.
- Giảm lỗi tích hợp nhờ contract tests.
- Giảm chi phí thay đổi nhờ refactoring được bảo vệ.
- Giảm sự cố nhờ kiểm soát dữ liệu có test concurrency.

Ngược lại, chuyển mọi lỗi khó về “làm sau” để tăng tốc tạm thời làm **tích lũy nợ và rủi ro**. Điều cần đo là **khả năng tạo giá trị đáng tin cậy**, không chỉ tốc độ gõ code.

## 19. Tổ chức và con người: tạo điều kiện cho một văn hóa học hỏi

### 19.1. Vòng cải tiến cần quyền nêu sự thật

Nếu một người kiểm thử bị trách khi báo lỗi vào ngày cuối Sprint, lần sau họ có thể im lặng. Nếu người trực CI bị phạt vì pipeline đỏ, họ có thể tắt kiểm tra. Khi đó **dữ liệu trở nên méo** và nhóm mất cơ hội quan sát vấn đề thật.

**An toàn tâm lý** là điều kiện để nêu nghi ngờ, xin giúp, phản biện và thừa nhận sai sót mà không sợ bị làm nhục hoặc trả đũa. Nó **không loại bỏ trách nhiệm**: mọi người vẫn phải giữ DoD, quy định dữ liệu và chuẩn nghề nghiệp; hành động nguy hiểm cần được xử lý theo chính sách.

### 19.2. Người lãnh đạo giúp nhóm học, không cung cấp sẵn mọi đáp án

Một người hỗ trợ cải tiến nên hỏi:

- Chúng ta thấy gì bằng dữ liệu hoặc quan sát trực tiếp?
- Người dùng/nhóm bị ảnh hưởng thế nào?
- Giải thích nào vẫn chỉ là giả định?
- Nếu thử một thay đổi nhỏ, dự đoán điều gì sẽ xảy ra?
- Giới hạn an toàn nào không được vượt?
- Người thực hiện có đủ quyền, thời gian, công cụ và chuyên môn không?
- Khi nào và ai sẽ kiểm tra kết quả?

Lãnh đạo phục vụ/servant leadership ở đây có nghĩa **gỡ trở ngại, phát triển năng lực và bảo vệ mục tiêu**, không phải “giao trách nhiệm rồi bỏ mặc”.

### 19.3. Học hỏi liên chức năng

Một cải tiến về đăng ký khóa học có thể cần:

- **Product Owner:** làm rõ nhu cầu, mục tiêu và ưu tiên.
- **Developers:** thiết kế/triển khai và kiểm chứng Increment.
- **Người kiểm thử:** khám phá kịch bản và đưa test theo rủi ro vào sớm.
- **Support:** cho biết tình huống người dùng thường gặp.
- **Vận hành:** cung cấp dữ liệu/khả năng quan sát và rủi ro rollout.
- **Security/privacy:** giữ các ranh giới bắt buộc.

Vòng cải tiến thất bại nếu chỉ cải thiện công việc của nhóm phát triển bằng cách **đẩy chờ đợi, rework hoặc hỗ trợ thủ công sang bộ phận khác**. Cần nhìn toàn chuỗi từ nhu cầu tới kết quả sử dụng thật.

### 19.4. Công khai giả thuyết và quyết định giúp tri thức không mất đi

Một **experiment log** có thể được lưu ở nơi nhóm đã dùng để theo dõi công việc, liên kết tới:

- Vấn đề và dữ liệu nền.
- Quyết định thử và người thực hiện.
- Các thay đổi đã áp dụng.
- Kết quả, giới hạn và tác động phụ.
- Quyết định giữ/đổi/hoàn tác.
- Chính sách/kiểm thử/PBI được cập nhật sau khi học.

Không cần tạo thêm một hệ thống báo cáo nặng. Cần bảo đảm **người mới tham gia vẫn hiểu tại sao có một chính sách**, không phải chỉ biết “trước giờ làm thế”.

## 20. Những phản mẫu thường làm đứt vòng cải tiến

| Phản mẫu | Vì sao nguy hiểm? | Cách sửa |
| --- | --- | --- |
| **Retro chỉ ghi cảm nghĩ, không có thử nghiệm** | Không biết hành động có tác dụng không. | Chọn một giả thuyết nhỏ, owner, số đo và mốc xem lại. |
| **Bắt đầu bằng công cụ/giải pháp yêu thích** | Có thể sửa nhầm vấn đề. | Mô tả quan sát, khoảng cách và cơ chế trước khi chọn đối sách. |
| **Quy lỗi “con người thiếu chủ động”** | Che nguyên nhân hệ thống, làm người khác ngại báo sự thật. | Dùng dữ liệu, quan sát và giả thuyết kiểm chứng được. |
| **Không có baseline** | Không biết cải thiện so với điều gì. | Ghi hiện trạng, phạm vi, thời gian và quy tắc đo. |
| **Thay nhiều thứ cùng lúc nhưng quy một nguyên nhân** | Không biết yếu tố nào có tác dụng. | Thử hẹp, ghi mọi thay đổi và confounders. |
| **Đổi metric sau khi xem kết quả để “thành công”** | Báo cáo sai lệch, mất niềm tin. | Công bố metric trước thử, ghi lý do nếu phải thay. |
| **Một chỉ số đại diện mọi thành công** | Dễ tăng tốc bằng cách giảm chất lượng. | Có metric chính và guardrails cân bằng. |
| **Xếp hạng cá nhân theo story point/commit/bug** | Tạo động lực tối ưu số liệu và che lỗi. | Dùng số đo phục vụ cải tiến hệ thống. |
| **Không xem item còn dở** | Chỉ nhìn item Finished, bỏ quên hàng đợi già. | Xem work item age, blocked và WIP cùng cycle time. |
| **Suy nguyên nhân chỉ từ trước–sau** | Có thể bị ảnh hưởng mùa vụ, loại việc, thay đổi khác. | Ghi giới hạn, dùng đối chứng phù hợp khi cần. |
| **Thử nghiệm lên người dùng khi kiểm soát an toàn chưa đạt** | Có thể gây dữ liệu sai, lộ thông tin hoặc thiệt hại. | Tuân thủ DoD, chính sách, đánh giá rủi ro và quyền quyết định. |
| **Dùng feature flag thay phân quyền** | Người dùng có thể gọi API bị ẩn trực tiếp. | Thực thi authn/authz phía server; flag chỉ hỗ trợ rollout. |
| **Tuyên bố Done bằng việc đổi trạng thái bảng** | Không phản ánh Increment thật, chỉ số bị bóp méo. | Giữ điều kiện hoàn tất và mốc đo minh bạch. |
| **Thử nhỏ nhưng không có cơ chế hoàn tác** | Tác động phụ kéo dài khi sai. | Đánh giá khả năng đảo ngược, dữ liệu và side effects. |
| **Không hỏi người dùng** | Cải thiện tốc độ xây thứ không có giá trị. | Quan sát outcome và phản hồi thực tế. |
| **Không hỏi người trực tiếp làm** | Bỏ sót nguyên nhân mà dashboard không thấy. | Gemba và trao đổi đa góc nhìn tôn trọng. |
| **Quá nhiều sáng kiến cải tiến cùng lúc** | Tăng WIP, nhiễu kết quả và quá tải. | Giới hạn số thử nghiệm, ưu tiên vấn đề quan trọng. |
| **Thử nghiệm có kết quả nhưng không ai quyết định** | Dữ liệu không dẫn tới thay đổi. | Đặt review date, owner và nhánh hành động rõ từ đầu. |
| **Một lần thử thất bại bị coi là không được đề xuất nữa** | Nhóm sợ học từ giả thuyết sai. | Phân biệt thử nghiệm an toàn có học với thực hiện thiếu trách nhiệm. |
| **Chuẩn hóa mà không xem lại** | Chính sách tốt ở bối cảnh cũ có thể gây nghẽn ở bối cảnh mới. | Theo dõi guardrails và đánh giá lại khi điều kiện đổi. |

## 21. Tổ chức một “experiment backlog” vừa đủ

### 21.1. Vì sao cần ưu tiên cả công việc cải tiến?

Nếu có 20 ý tưởng sau Retro, nhóm không nên khởi động cả 20. Mỗi thử nghiệm tốn **năng lực, sự tập trung và chi phí đo**, có thể cản trở Sprint Goal hoặc cam kết vận hành nếu không sắp xếp.

Một danh sách cải tiến nhỏ có thể gồm:

| ID | Vấn đề | Giả thuyết | Tác động nếu đúng | Chi phí/rủi ro thử | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| IMP-01 | Verify chờ lâu | Tích hợp sớm giảm hàng đợi | Có thêm Increment Done sớm | Thấp–vừa | Đang thử |
| IMP-02 | CI thường báo sai | Cách ly dữ liệu test giảm flaky | Feedback đáng tin hơn | Vừa | Chờ |
| IMP-03 | Người học hỏi trạng thái | Tra trạng thái thật giảm ticket | Tự phục vụ tốt hơn | Vừa–cao vì liên quan dữ liệu | Cần thiết kế an toàn |
| IMP-04 | Retro không có hành động tiếp | Ghi owner và review date tăng việc được kiểm chứng | Cải tiến bền vững | Thấp | Sẵn sàng |

Các trạng thái trên là **ví dụ minh họa**, không phải quy tắc của Scrum hay Kanban. Nhóm có thể lưu ý tưởng cải tiến trong Product Backlog nếu gắn với sản phẩm hoặc trong một danh sách cải tiến riêng nếu phù hợp, nhưng **không để các danh sách bị tách làm mất bức tranh năng lực chung**.

### 21.2. Chọn thử nghiệm tiếp theo như thế nào?

Có thể cân nhắc:

1. **Tác động:** vấn đề ảnh hưởng người dùng, chất lượng hoặc luồng công việc ra sao?
2. **Khả năng học:** thử nghiệm có giúp phân biệt các giả thuyết quan trọng không?
3. **Chi phí và rủi ro:** có thể thử an toàn, hoàn tác và đo được không?
4. **Phụ thuộc:** cần ai, môi trường hoặc dữ liệu nào trước khi thử?
5. **Năng lực:** có ai thực sự thực hiện và xem lại được không?
6. **Mức khẩn cấp:** có sự cố hay kiểm soát bắt buộc cần xử lý ngay?

Một ý tưởng **rẻ nhưng không giải quyết vấn đề quan trọng** không phải luôn đáng ưu tiên. Một vấn đề an toàn nghiêm trọng không nên bị xếp dưới cùng vì “thử mất nhiều công”.

### 21.3. Experiment board tối giản

~~~mermaid
flowchart LR
    A["Ý tưởng cải tiến"] --> B["Làm rõ vấn đề, baseline, guardrails"]
    B --> C["Sẵn sàng thử"]
    C --> D["Đang thử"]
    D --> E["Đánh giá kết quả"]
    E --> F["Giữ / chuẩn hóa"]
    E --> G["Điều chỉnh / thử tiếp"]
    E --> H["Hoàn tác / kết thúc"]
    G --> B
~~~

Đây là luồng **học hỏi của thử nghiệm**, không được dùng như bảng phê duyệt làm chậm mọi thay đổi. Nhóm nên giới hạn lượng thử nghiệm đang chạy và xem chúng có tạo giá trị hay không.

### 21.4. Mẫu “một thẻ thử nghiệm” có thể sao chép

~~~markdown
## IMP-XX — [Tên cải tiến]

**Vấn đề thực tế:** ...
**Đối tượng bị ảnh hưởng:** ...
**Hiện trạng/baseline:** ... (khoảng đo, nguồn và quy tắc tính)
**Trạng thái mục tiêu:** ...

**Giả thuyết:** Nếu ... thì ... vì ...
**Điều có thể bác bỏ giả thuyết:** ...

**Thử nghiệm nhỏ nhất:** ...
**Phạm vi và thời gian thử:** ...
**Owner/phối hợp:** ...
**Metric chính:** ...
**Tín hiệu bổ sung:** ...
**Guardrails / điều kiện dừng:** ...
**Khả năng hoàn tác và rủi ro dữ liệu:** ...

**Kết quả quan sát:** ...
**Giới hạn/yếu tố gây nhiễu:** ...
**So với dự đoán:** ...
**Quyết định:** Giữ / Điều chỉnh / Hoàn tác / Thử khác
**Bài học và việc tiếp:** ...
**Ngày xem lại:** ...
~~~

Nếu thử nghiệm chỉ là thay đổi working agreement nhỏ trong một đội, bản ghi có thể ngắn hơn. Với thử nghiệm tác động người dùng thật, tài chính hoặc dữ liệu, cần **đánh giá chuyên môn và điều kiện được phép** tương ứng, không lấy mẫu một trang thay cho nghĩa vụ cần thiết.

## 22. Bài tập thực hành và gợi ý lời giải

### Bài tập 1 — Tách quan sát, giả thuyết và giải pháp

Một đội nói:

1. “Tuần này có 7 PR chờ review lâu hơn một ngày.”
2. “Developer thiếu chủ động nên review chậm.”
3. “Chúng ta phải mua một công cụ quản lý review mới.”
4. “Có thể người review duy nhất đang là điểm nghẽn.”
5. “Nếu có người review dự phòng, thời gian chờ sẽ giảm.”

**Yêu cầu:** phân loại từng phát biểu là sự kiện, diễn giải/giả thuyết hay giải pháp. Nêu thông tin còn thiếu để kiểm chứng giả thuyết chính.

**Gợi ý lời giải:**

- **(1)** là quan sát có thể kiểm chứng, nhưng cần biết tổng số PR, khoảng thời gian và cách định nghĩa “chờ”.
- **(2)** là phán đoán quy lỗi thiếu bằng chứng, không phải mô tả vấn đề tốt.
- **(3)** là một giải pháp được đề nghị, chưa rõ cơ chế giảm chờ.
- **(4)** là giả thuyết về nút thắt.
- **(5)** là dự đoán/đối sách có thể thử, cần bổ sung phạm vi, metric và guardrail.

Có thể kiểm tra thời gian chờ theo reviewer, loại PR, lịch trực/nghỉ phép và khả năng có người dự phòng đủ chuyên môn. Nếu phần lớn thời gian do pipeline chạy chậm thay vì chờ reviewer, giả thuyết cần sửa.

### Bài tập 2 — Viết giả thuyết có thể bác bỏ

Vấn đề: nhóm có nhiều PBI chưa Done khi kết thúc Sprint. Trong ba Sprint, phần lớn hạng mục bị chặn ở bước kiểm thử tích hợp. Một đề xuất là “hãy áp dụng pair programming cho toàn bộ công việc”.

**Yêu cầu:** viết giả thuyết đúng mẫu **Nếu… thì… vì…**, với baseline, một metric chính, hai guardrails và một tình huống khiến nhóm bác bỏ giả thuyết.

**Ví dụ đáp án:**

> Nếu các PBI có phụ thuộc frontend–API–DB được làm rõ bằng ví dụ và phát triển theo lát cắt dọc ngay từ đầu Sprint, thì thời gian chờ kiểm thử tích hợp sẽ giảm so với các PBI tương đương, vì xung đột hợp đồng và lỗi tích hợp xuất hiện sớm hơn.

- **Baseline:** thời gian chờ ở Verify và thời điểm có bản tích hợp đầu tiên trong ba Sprint trước.
- **Metric chính:** work item age tại Verify hoặc tổng thời gian chờ Verify theo cách đo nhất quán.
- **Guardrails:** không bỏ DoD; không tăng lỗi hậu phát hành; cũng có thể xem tải người kiểm thử.
- **Bác bỏ/điều chỉnh:** nếu tích hợp sớm nhưng thời gian chờ không đổi và dữ liệu cho thấy môi trường bị nghẽn thì cần kiểm tra giả thuyết môi trường thay vì tiếp tục mở rộng pairing.

Không bắt buộc dùng giải pháp pairing cho mọi hạng mục chỉ vì đó là ý tưởng được nêu đầu tiên.

### Bài tập 3 — Chọn thử nghiệm nhỏ nhất

Đội có vấn đề **chỉ một chuyên gia biết kiểm tra migration dữ liệu**. Khi chuyên gia vắng, mọi thay đổi DB bị chặn. Có ba đề nghị:

- A. Đổi hoàn toàn kiến trúc database.
- B. Cho một kỹ sư khác pair với chuyên gia, viết checklist kiểm chứng migration và thử trên một thay đổi rủi ro thấp.
- C. Bỏ bước review migration để không phải chờ.

**Yêu cầu:** chọn thử nghiệm ban đầu, giải thích khả năng hoàn tác và hai chỉ số kiểm chứng.

**Gợi ý:** **B** thường là thử nghiệm nhỏ, có cơ hội chia sẻ tri thức và không bỏ kiểm soát. Đo thời gian chờ người có quyền review và số lần migration phải làm lại hoặc lỗi trong môi trường thử. A có chi phí/rủi ro lớn khi chưa chứng minh nguyên nhân; C hạ chuẩn chất lượng và có thể gây hại.

### Bài tập 4 — Đọc kết quả trước–sau

Dữ liệu giả định:

| Kỳ | PBI hoàn tất | Cycle time trung vị | Lỗi sau phát hành |
| --- | ---: | ---: | ---: |
| Trước thử | 12 | 8 ngày | 1 |
| Sau thử WIP limit | 13 | 5 ngày | 3 |

**Câu hỏi:**

1. Chỉ số nào có vẻ cải thiện?
2. Vì sao chưa thể gọi thử nghiệm thành công?
3. Nên thu thập thêm những dữ liệu gì?
4. Nhóm cần làm gì nếu ba lỗi sau phát hành đều nghiêm trọng?

**Gợi ý:** cycle time trung vị giảm, throughput của kỳ tăng nhẹ nếu hai kỳ cùng độ dài; nhưng số lỗi tăng là guardrail cần phân tích. Phải xem severity, lượng người dùng, loại item, DoD và cơ chế kiểm thử. Nếu lỗi nghiêm trọng, ưu tiên ứng cứu, bảo vệ người dùng và kiểm tra tác động trước khi tiếp tục mở rộng chính sách; không đánh đổi chất lượng lấy cycle time.

### Bài tập 5 — Tính tỷ lệ và nêu giới hạn diễn giải

Nhóm thử thêm trang tra trạng thái sau timeout:

- Trước: **80 ticket** về trạng thái trên **2.000** học viên có thao tác đăng ký.
- Sau: **60 ticket** về trạng thái trên **2.100** học viên tương ứng.

**Yêu cầu:**

1. Tính tỷ lệ cho hai kỳ.
2. Tính chênh lệch điểm phần trăm gần đúng.
3. Giải thích vì sao chưa khẳng định thay đổi là nguyên nhân duy nhất.
4. Nêu hai guardrails liên quan sản phẩm.

**Gợi ý lời giải:**

\[
\text{Trước}=\frac{80}{2.000}\times100\%=4\%.
\]

\[
\text{Sau}=\frac{60}{2.100}\times100\%\approx2{,}86\%.
\]

\[
\text{Chênh lệch}\approx4\%-2{,}86\%=1{,}14\text{ điểm phần trăm}.
\]

Phải xét sự khác nhau về người dùng, mức tải, loại khóa, cách ghi ticket và các thay đổi khác. Guardrails gồm **không tạo đăng ký trùng** và **không cho người khác tra dữ liệu trái quyền**; có thể xem thêm độ trễ và khả năng dùng thực tế.

### Bài tập 6 — Thiết kế quyết định sau một thử nghiệm thất bại

Nhóm thêm một cuộc họp 30 phút mỗi ngày để giảm chờ giữa frontend và backend. Sau hai tuần:

- Thời gian chờ API contract không cải thiện.
- Số giờ họp tăng.
- Người làm nói họ ít thời gian tập trung hơn.
- Contract test hiện vẫn không có.

**Yêu cầu:** viết kết luận theo các mục **quan sát, giả thuyết, giới hạn, guardrail, quyết định và hành động tiếp**.

**Gợi ý:** giả thuyết “thêm đồng bộ sẽ giảm chờ” chưa được dữ liệu ủng hộ; có tín hiệu tác dụng phụ về tải thời gian. Nhóm có thể dừng cuộc họp thử, làm rõ lý do hợp đồng API thay đổi/chờ và thử dùng contract test với chính sách thông báo. Không tuyên bố người tham gia “không hợp tác” chỉ vì biện pháp đầu tiên không hiệu quả.

### Bài tập 7 — Quan sát việc cải tiến WIP có thực sự tác động toàn luồng

Nhóm giảm WIP từ 8 xuống 4. Thẻ ở Developing ít hơn, nhưng rất nhiều thẻ ở Review vẫn chờ trên 10 ngày. Dashboard chỉ báo **cycle time của item Done**, không hiển thị item đang dở.

**Yêu cầu:** đề xuất ba phép đo/bằng chứng bổ sung và hai thay đổi thử nghiệm tiếp theo.

**Gợi ý:**

- Xem **work item age** của item Review chưa xong.
- Ghi nguyên nhân blocked, quyền reviewer, thời gian chờ theo bước.
- Xem throughput, chất lượng rework và phân bố cycle time, không chỉ trung vị.
- Thử người review dự phòng có chuyên môn hoặc đưa kiểm chứng API/test vào sớm.
- Chỉ thử thay đổi WIP mới sau khi hiểu điểm nghẽn, không ép thẻ Done khi chưa đạt.

### Bài tập 8 — Phân biệt thử nghiệm an toàn và thử nghiệm không được phép

Một đội muốn tăng tỷ lệ đăng ký khóa có thu học phí. Họ đề nghị:

1. Thử hai cách diễn đạt thông báo xác nhận sau khi cả hai đã được kiểm chứng đúng và được phép sử dụng.
2. Trong nhóm A, tắt kiểm tra quyền và idempotency để biết tỷ lệ hoàn tất có tăng không.
3. Thử prototype trang thanh toán với dữ liệu giả và người tham gia đã đồng ý.
4. Đưa schema mới vào production không có kiểm tra tương thích để xem nó lỗi ở đâu.

**Câu hỏi:** cách nào có thể là thử nghiệm phù hợp và vì sao? Những yêu cầu bảo mật, riêng tư và chất lượng nào không được bỏ?

**Gợi ý:** (1) có thể cân nhắc thử theo chính sách, với giới hạn đo và dữ liệu; (3) có thể phù hợp cho nghiên cứu trải nghiệm khi tuân thủ sự đồng ý và dữ liệu an toàn. (2) và (4) không phải cách thử phù hợp vì cố tình bỏ bảo vệ quan trọng và có thể gây hại. A/B không làm thay đổi nghĩa vụ phân quyền hoặc tính đúng đắn giao dịch.

### Bài tập 9 — Thiết kế một vòng PDCA cho CI

Thông tin:

- CI bắt buộc thường mất **35 phút** từ lúc push tới kết quả.
- Một số job chờ runner lâu; một số integration tests flaky.
- Đội dự tính tăng tốc bằng cách bỏ integration tests.

**Yêu cầu:** điền **Plan, Do, Check, Act** để học điều gì đang gây chậm, giảm thời gian phản hồi mà không giảm độ tin cậy.

**Gợi ý:**

- **Plan:** đo thời gian chờ runner, setup, unit/integration test; giả thuyết chạy song song và sửa dữ liệu test giúp giảm thời gian.
- **Do:** thử phân tầng, song song các nhóm test độc lập, cách ly dữ liệu theo phạm vi được phép.
- **Check:** so feedback time, flaky rate, mainline health, test coverage theo rủi ro, lỗi sau merge; xác nhận mọi check bắt buộc còn chạy.
- **Act:** giữ thay đổi tốt, sửa phần không ổn định hoặc hoàn tác nếu chất lượng kém; lên thử nghiệm tiếp nếu nút thắt thực là runner capacity.

### Bài tập 10 — Retrospective có thực sự dẫn đến cải tiến?

Một nhóm Scrum mỗi Retro đều ghi “cần giao tiếp tốt hơn”. Sau bốn Sprint, không có thay đổi nào rõ ràng. Sprint Review lại liên tục nhận phản hồi rằng trạng thái đăng ký khó hiểu.

**Yêu cầu:** đề xuất một thử nghiệm cho **cách làm** và một thử nghiệm cho **sản phẩm**, ghi owner và điều kiện kiểm chứng khác nhau.

**Gợi ý:**

- **Cách làm:** trước khi xây PBI có trạng thái bất đồng bộ, tổ chức phiên làm rõ ngắn giữa PO, Developers, QA và support; thêm ví dụ retry/timeout. Xem số lần phải làm rõ sau code, lỗi phát hiện muộn và chất lượng DoD.
- **Sản phẩm:** thử luồng tự tra trạng thái trên bản tích hợp đã kiểm chứng cho nhóm người dùng phù hợp. Xem tỷ lệ hoàn tất tự phục vụ, hiểu thông báo và các guardrails dữ liệu/quyền.

Product Owner quyết định thứ tự Product Backlog; Developers tạo Increment đạt DoD; Scrum Master hỗ trợ hiệu quả Scrum Team. Hai thử nghiệm có thể liên quan nhưng **không được lấy chỉ số của thử nghiệm này làm bằng chứng trực tiếp cho thử nghiệm kia**.

### Bài tập 11 — Ghi kết quả có tính đến yếu tố gây nhiễu

Nhóm thử giảm WIP trong hai Sprint:

- Sprint nền có một thành viên nghỉ một tuần và hệ thống test bị sự cố.
- Sprint thử có đầy đủ nhân sự và không gặp sự cố môi trường.
- Cycle time giảm đáng kể.

**Yêu cầu:** hãy viết **hai câu báo cáo chính xác** và **một câu không nên viết**.

**Ví dụ chính xác:**

> “Trong Sprint thử, cycle time quan sát giảm so với Sprint nền theo cùng mốc đo. Tuy nhiên, điều kiện năng lực và môi trường kiểm thử khác nhau, nên chưa đủ bằng chứng khẳng định giảm WIP là nguyên nhân duy nhất.”

**Ví dụ không nên viết:**

> “Giảm WIP đã chứng minh làm nhóm nhanh hơn 40% trong mọi Sprint.”

Nhóm có thể tiếp tục theo dõi nhiều kỳ có điều kiện tương đương và kiểm tra trực tiếp hàng đợi/điểm nghẽn.

### Bài tập 12 — Viết thẻ thử nghiệm hoàn chỉnh

Chọn một vấn đề thật hoặc tình huống học tập: PR review lâu, backlog nhiều item mơ hồ, học viên không biết trạng thái đăng ký, CI flaky hoặc lỗi tích hợp phát hiện muộn.

Hãy điền đầy đủ:

1. **Bằng chứng quan sát** với đối tượng, phạm vi, khoảng thời gian.
2. **Khoảng cách cần cải thiện** và giá trị mong muốn.
3. **Hai giả thuyết nguyên nhân** có thể kiểm chứng.
4. **Một thử nghiệm nhỏ** ưu tiên, lý do chọn thay vì thử cả hai cùng lúc.
5. **Baseline, metric chính và hai guardrails.**
6. **Thời điểm xem kết quả**, người có quyền quyết và trường hợp cần dừng sớm.
7. **Ba kết cục giả định:** có cải thiện, không cải thiện, chưa đủ bằng chứng; quyết định tương ứng.

**Gợi ý đánh giá bài làm:**

| Tiêu chí | Bài làm đạt khi |
| --- | --- |
| **Vấn đề rõ** | Không nhầm hoạt động muốn làm với kết quả cần đạt. |
| **Giả thuyết có thể bác bỏ** | Có cơ chế, dự đoán và bằng chứng có thể phủ định. |
| **Thử nghiệm nhỏ, an toàn** | Có giới hạn và không bỏ kiểm soát bắt buộc. |
| **Phép đo nhất quán** | Định nghĩa mốc, mẫu và cách so sánh. |
| **Guardrails hợp lý** | Không đổi tốc độ lấy lỗi nghiêm trọng/riêng tư/quá tải. |
| **Quyết định có căn cứ** | Không suy nhân quả tuyệt đối từ một mẫu nhỏ. |
| **Hành động tiếp theo** | Có owner và điều kiện kiểm chứng học hỏi sau thử. |

## 23. Checklist để chạy một vòng cải tiến có thể kiểm chứng

### Trước khi chọn giải pháp

- [ ] Đã nêu **người dùng hoặc dòng công việc** nào bị ảnh hưởng.
- [ ] Đã mô tả hiện tượng bằng ít nhất một nguồn bằng chứng thực tế.
- [ ] Phân biệt sự kiện, cách diễn giải, giả định và giải pháp được đề xuất.
- [ ] Đã xem người trực tiếp làm việc/nhận giá trị nghĩ gì trong bối cảnh phù hợp.
- [ ] Đã ghi dữ liệu nền, phạm vi và mốc đo nếu có thể.
- [ ] Có trạng thái mục tiêu gắn với giá trị thay vì một hoạt động tùy ý.
- [ ] Các rủi ro cần kiểm soát được nêu trước, không chờ sau thử mới xem.

### Khi hình thành giả thuyết

- [ ] Giả thuyết có cấu trúc **nếu… thì… vì…** và có thể sai.
- [ ] Có thể nêu bằng chứng nào sẽ bác bỏ hoặc làm yếu giả thuyết.
- [ ] Có ít nhất một cách kiểm tra nguyên nhân, không chỉ đo output của giải pháp.
- [ ] Đã cân nhắc những nguyên nhân khác, phụ thuộc và điều chưa biết.
- [ ] Không kết luận vấn đề là do cá nhân thiếu nỗ lực khi chưa có bằng chứng.
- [ ] Giải pháp được lựa chọn có phạm vi **đủ nhỏ để học và phù hợp khả năng hoàn tác**.

### Trước khi thử nghiệm

- [ ] Có owner, người phối hợp và người có quyền quyết định những thay đổi rủi ro.
- [ ] Có ngày bắt đầu, phạm vi thử và thời điểm xem kết quả.
- [ ] Đã chọn metric chính đúng với vấn đề và ghi quy tắc tính.
- [ ] Có guardrails về DoD, lỗi, dữ liệu, bảo mật, tải công việc và các nghĩa vụ khác khi phù hợp.
- [ ] Có điều kiện dừng sớm và hành động giảm tác động khi cần.
- [ ] Với người dùng thật, các kiểm soát và điều kiện phát hành bắt buộc đã đạt.
- [ ] Không dùng thử nghiệm làm cách né review chuyên môn hoặc yêu cầu pháp lý.

### Trong quá trình thử

- [ ] Thực hiện đúng phạm vi hoặc ghi rõ mọi sai lệch.
- [ ] Thu bằng chứng tương ứng với dự đoán và tác động phụ.
- [ ] Không thay metric chỉ để làm kết quả đẹp hơn.
- [ ] Theo dõi cả item đang dở, lỗi, phản hồi người dùng và phụ thuộc khi liên quan.
- [ ] Nếu guardrail nghiêm trọng bị vi phạm, xử lý ngay theo chính sách.
- [ ] Không dùng số đo để đổ lỗi hoặc ép cá nhân làm sai chuẩn.

### Khi đánh giá và tiếp tục

- [ ] Đối chiếu quan sát với **dự đoán ban đầu**.
- [ ] Ghi cỡ mẫu, khoảng thời gian và yếu tố gây nhiễu.
- [ ] Phân biệt “có tín hiệu cải thiện” với “đã chứng minh nguyên nhân”.
- [ ] Có quyết định rõ: **giữ, điều chỉnh, hoàn tác hoặc thu thêm bằng chứng**.
- [ ] Người chịu trách nhiệm cập nhật working agreement, DoW, test, DoD, runbook hoặc backlog khi phù hợp.
- [ ] Không khẳng định output/throughput tăng đồng nghĩa outcome hoặc chất lượng tăng.
- [ ] Có điều kiện quan sát lại khi quy mô, loại việc hoặc rủi ro thay đổi.
- [ ] Bài học đủ rõ để người mới hiểu **vì sao nhóm chọn cách làm hiện tại**.

Checklist này hỗ trợ **một cuộc trao đổi học hỏi**. Không cần biến mọi thay đổi nhỏ thành một quy trình tài liệu dài, nhưng **những rủi ro quan trọng phải có mức kiểm chứng tương xứng**.

## 24. Tổng kết

**Tạo vòng cải tiến từ quan sát, giả thuyết đến thử nghiệm** giúp nhóm Agile không bị kẹt giữa hai cực đoan: **hành động theo cảm tính** và **đo lường vô tận nhưng không quyết định**.

Trình tự thực hành:

1. **Quan sát:** nhìn công việc, người dùng và dữ liệu thật; ghi sự kiện trước khi diễn giải.
2. **Làm rõ vấn đề:** mô tả khoảng cách giữa trạng thái hiện tại và mục tiêu có giá trị.
3. **Đặt giả thuyết:** nêu cơ chế có thể sai, dự đoán và bằng chứng để kiểm chứng.
4. **Thử nhỏ, an toàn:** giới hạn phạm vi, có quyền/nguồn lực, baseline, metric và guardrails.
5. **Kiểm tra kết quả:** so dự đoán với thực tế, nhận diện yếu tố gây nhiễu và mức bất định.
6. **Quyết định và học:** duy trì, điều chỉnh, hoàn tác hoặc thử tiếp; có owner và bước theo dõi.
7. **Lặp lại:** chuẩn hóa điều hữu ích nhưng sẵn sàng thay đổi khi bối cảnh đổi.

**Scrum** cung cấp những cơ hội kiểm tra–thích ứng qua Sprint Review, Retrospective và công việc hằng ngày. **Kanban** cho phép nhìn luồng, kiểm soát WIP và cải thiện chính sách theo dữ liệu. **XP** tạo vòng phản hồi kỹ thuật ngắn bằng test, CI và thay đổi nhỏ. **Lean/Kaizen** giúp nhóm đến gần vấn đề thực, tôn trọng con người và thử đối sách dựa trên bằng chứng.

Điểm chung của các cách làm không phải **có thật nhiều sáng kiến** mà là **học nhanh về điều quan trọng, giao giá trị đáng tin cậy và cải thiện hệ thống làm việc mà không đánh đổi an toàn hoặc trách nhiệm với người dùng**.

### Thuật ngữ chính

| Thuật ngữ | Ý nghĩa |
| --- | --- |
| **Continuous improvement / Kaizen** | Cải tiến liên tục cách làm và kết quả dựa trên quan sát, thử nghiệm và học hỏi. |
| **PDCA** | Plan–Do–Check–Act: lập kế hoạch, thực hiện, kiểm tra kết quả, điều chỉnh/chuẩn hóa. |
| **PDSA** | Plan–Do–Study–Act: nhấn mạnh nghiên cứu và học từ kết quả thay vì chỉ đánh dấu đạt/không đạt. |
| **Build–Measure–Learn** | Vòng tạo cách kiểm chứng, đo và học về giả định sản phẩm. |
| **Gemba** | Nơi công việc/giá trị thực sự diễn ra; quan sát để hiểu hệ thống. |
| **Baseline** | Hiện trạng làm mốc so sánh, có phạm vi, khoảng thời gian và quy tắc đo. |
| **Problem statement** | Mô tả khoảng cách cần cải thiện, không áp đặt giải pháp. |
| **Target condition** | Trạng thái mục tiêu gần giúp định hướng các bước thử nghiệm kế tiếp. |
| **Hypothesis** | Giả thuyết có cơ chế, dự đoán và khả năng bị bác bỏ bởi bằng chứng. |
| **Experiment** | Thử một thay đổi có phạm vi, đo lường và điều kiện an toàn để học về giả thuyết. |
| **Falsifiability** | Khả năng nêu bằng chứng có thể cho thấy một giả thuyết sai. |
| **Guardrail metric** | Chỉ số/điều kiện bảo vệ chất lượng, an toàn hoặc tác động ngoài dự kiến khi cải thiện metric chính. |
| **Confounder** | Yếu tố khác có thể gây sai lệch cách diễn giải kết quả trước–sau hoặc giữa các nhóm. |
| **Leading / lagging indicators** | Tín hiệu sớm của cơ chế / tín hiệu kết quả xuất hiện sau một thời gian. |
| **Outcome / output / activity** | Kết quả thực tế người dùng / sản phẩm được tạo / hoạt động đã thực hiện. |
| **A3 problem solving** | Trình bày ngắn gọn bối cảnh, vấn đề, nguyên nhân, đối sách và kết quả để trao đổi. |
| **Improvement Kata** | Thói quen cải tiến từ hướng đi, hiện trạng, target condition tới thử nghiệm và học hỏi. |
| **Five Whys** | Kỹ thuật đào sâu nguyên nhân bằng các câu hỏi “vì sao”, cần kiểm chứng các mắt xích. |
| **WIP** | Work in Progress: số item đã bắt đầu nhưng chưa Finished theo workflow. |
| **Cycle time** | Thời gian Started tới Finished của item hoàn tất theo ranh giới đo. |
| **Work item age** | Thời gian item đang dở đã tồn tại kể từ Started. |
| **Throughput** | Số item Finished trong một khoảng thời gian. |
| **Little's Law** | Quan hệ giữa WIP, thông lượng và thời gian trung bình trong hệ thống khi thỏa điều kiện áp dụng. |
| **Definition of Workflow (DoW)** | Cách nhóm Kanban định nghĩa và vận hành luồng, gồm ranh giới, chính sách và kiểm soát WIP. |
| **Service Level Expectation (SLE)** | Kỳ vọng có tính xác suất về thời gian hoàn tất theo workflow và dữ liệu phù hợp. |
| **Definition of Done (DoD)** | Cam kết chất lượng chính thức của Increment trong Scrum. |
| **TDD / CI** | Phát triển dẫn dắt bởi test / tích hợp liên tục để nhận phản hồi kỹ thuật sớm. |
| **Psychological safety** | Môi trường có thể nêu vấn đề, hỏi và phản biện mà không sợ bị làm nhục hoặc trả đũa. |
| **Experiment log** | Bản ghi vấn đề, giả thuyết, thay đổi, kết quả, giới hạn và quyết định sau thử nghiệm. |




