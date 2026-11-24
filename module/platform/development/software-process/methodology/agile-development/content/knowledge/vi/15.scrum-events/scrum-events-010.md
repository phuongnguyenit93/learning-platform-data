# Phân biệt mục đích sự kiện với báo cáo tình trạng hoặc phê duyệt hình thức

Một Scrum Team có thể duy trì đầy đủ lịch họp nhưng vẫn giao sản phẩm chậm. Mỗi sáng, Developers đọc tiến độ cho quản lý. Đầu Sprint, một người giao danh sách task cố định. Cuối Sprint, nhóm trình chiếu những màn hình đã lập trình để xin chữ ký nghiệm thu. Sau đó, cả nhóm họp rút kinh nghiệm nhưng không thay đổi cách làm. **Có nhiều cuộc họp không có nghĩa đang thực hành Scrum hiệu quả.**

Theo **Scrum Guide 2020**, các sự kiện Scrum tạo cơ hội chính thức để **kiểm tra (inspection) và thích ứng (adaptation)**. Chúng hỗ trợ tính **minh bạch (transparency)**, nhờ đó Scrum Team có thể quan sát thực tế, phát hiện khác biệt giữa dự định và kết quả, rồi điều chỉnh một cách có trách nhiệm. Sự kiện không được thiết kế chủ yếu để cấp dưới báo cáo cho cấp trên hay để tổ chức dựng thêm các cửa phê duyệt mang tính hình thức.

Bài học thuộc chương **Sự kiện Scrum** của mô-đun **AGILE_DEVELOPMENT**. Chúng ta sẽ phân biệt rõ mục đích của **Sprint, Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective**, cách chúng liên kết với Product Goal, Sprint Goal, Product Backlog, Increment và Definition of Done; sau đó thực hành với một sản phẩm học trực tuyến. Các ví dụ cũng cho thấy cách kết hợp phản hồi sớm, user story, backlog, kỹ thuật XP và phép đo dòng công việc để cải tiến liên tục.

**Sau bài học, bạn có thể:**

- Giải thích vì sao Scrum event là cơ hội kiểm tra/thích ứng thay vì buổi báo cáo tình trạng.
- Nêu mục đích, thành phần tham gia và timebox của từng sự kiện theo Scrum Guide 2020.
- Phân biệt Sprint Review với kiểm thử chấp nhận, quyết định phát hành và phê duyệt tuân thủ.
- Nhận biết một sự kiện bị biến dạng thành nghi thức quản lý hình thức.
- Đề xuất cách tổ chức trao đổi để mỗi sự kiện tạo ra **quyết định, bằng chứng hoặc kế hoạch điều chỉnh hữu ích**.
- Đánh giá cải tiến bằng kết quả sản phẩm và chất lượng phối hợp, không chỉ bằng số cuộc họp.

## 1. Nền tảng: sự kiện tồn tại để kiểm tra và thích ứng

Scrum sử dụng **empiricism (chủ nghĩa thực nghiệm)** để xử lý những công việc phức tạp: hiểu biết được hình thành từ trải nghiệm và quyết định dựa trên điều đã quan sát. Ba trụ cột là:

1. **Minh bạch:** Những người liên quan có cùng cách hiểu về mục tiêu, trạng thái, chất lượng, kết quả và rủi ro.
2. **Kiểm tra:** Xem các artifact và mức tiến triển hướng tới mục tiêu để phát hiện thay đổi hoặc vấn đề đáng chú ý.
3. **Thích ứng:** Điều chỉnh kế hoạch, backlog, sản phẩm hay cách làm khi có thông tin mới.

Không có minh bạch, một bản báo cáo “mọi việc đều xanh” có thể che khuất lỗi kiểm thử. Không kiểm tra, nhóm chỉ đi theo kế hoạch cũ. Không thích ứng, việc thu thập ý kiến cuối Sprint không tạo ra giá trị học hỏi.

~~~mermaid
flowchart LR
    A["Minh bạch: mục tiêu, công việc, Increment, dữ liệu"] --> B["Kiểm tra: điều gì thực sự xảy ra?"]
    B --> C["Thích ứng: nên thay đổi điều gì?"]
    C --> D["Hành động và Increment kế tiếp"]
    D --> A
~~~

Scrum Guide xem các sự kiện là cơ hội chính thức để kiểm tra và thích ứng, nhằm giảm nhu cầu phát sinh thêm các cuộc họp không định trước. **Điều đó không cấm nhóm trao đổi khi cần**. Developers vẫn có thể ghép cặp, trao đổi nghiệp vụ, xử lý sự cố hoặc kiểm thử cùng nhau bên ngoài các event.

### Một sự kiện hiệu quả cần kết thúc bằng điều gì?

Không nhất thiết mỗi event phải sinh thêm biên bản hoặc một tài liệu dài. Nhưng người tham gia nên có thể trả lời:

- **Đã kiểm tra điều gì?** Sprint Goal, Product Goal, Increment, Product Backlog hay hiệu quả làm việc?
- **Bằng chứng nào được xem xét?** Phần mềm dùng được, tình huống kiểm thử, ý kiến stakeholder, dòng công việc, lỗi thực tế?
- **Điều gì được quyết định hoặc điều chỉnh?** Kế hoạch trong Sprint, thứ tự backlog, mục tiêu kiểm chứng hoặc thử nghiệm cải tiến?
- **Ai chịu trách nhiệm cho quyết định tiếp theo?** Có đúng với các accountability của Scrum?

Một cuộc họp kết thúc đúng giờ nhưng không làm rõ những câu hỏi thích hợp có thể đạt **timebox** mà chưa đạt **mục đích**.

## 2. Năm sự kiện của Scrum: Sprint và bốn sự kiện bên trong

**Sprint** là sự kiện bao trùm, chứa các sự kiện còn lại và công việc tạo Increment. Sprint có độ dài cố định **một tháng hoặc ngắn hơn**; Sprint mới bắt đầu ngay sau khi Sprint trước kết thúc.

Bốn sự kiện chính thức diễn ra trong Sprint là **Sprint Planning, Daily Scrum, Sprint Review và Sprint Retrospective**.

| Sự kiện | Mục đích chủ yếu | Người tham gia theo Scrum | Timebox |
| --- | --- | --- | --- |
| **Sprint** | Tạo nhịp kiểm tra/thích ứng ổn định để tiến tới Product Goal và tạo Increment có giá trị | Scrum Team thực hiện công việc trong Sprint | **Tối đa một tháng** |
| **Sprint Planning** | Khởi đầu Sprint bằng cách làm rõ *vì sao*, *cái gì* và *làm thế nào* để tạo giá trị | Toàn **Scrum Team**; có thể mời người khác tư vấn khi cần | **Tối đa 8 giờ** cho Sprint một tháng |
| **Daily Scrum** | Kiểm tra tiến độ hướng tới Sprint Goal, điều chỉnh Sprint Backlog và kế hoạch kế tiếp | **Developers**; Product Owner hoặc Scrum Master tham gia với tư cách Developers nếu đang chủ động làm việc trên Sprint Backlog | **15 phút** |
| **Sprint Review** | Kiểm tra kết quả Sprint, thảo luận tiến triển hướng tới Product Goal và thích ứng điều cần làm tiếp | **Scrum Team và các stakeholder chủ chốt được mời** | **Tối đa 4 giờ** cho Sprint một tháng |
| **Sprint Retrospective** | Lập kế hoạch cải thiện **chất lượng và hiệu quả** của Scrum Team | **Scrum Team** | **Tối đa 3 giờ** cho Sprint một tháng |

Với Sprint ngắn hơn một tháng, các sự kiện như Planning, Review và Retrospective thường ngắn hơn. **Daily Scrum vẫn là 15 phút**. Timebox là giới hạn tối đa, không phải mục tiêu phải sử dụng hết.

Một dòng thời gian đơn giản:

~~~mermaid
flowchart LR
    A["Sprint Planning"] --> B["Công việc Sprint + Daily Scrum mỗi ngày làm việc"]
    B --> C["Sprint Review"]
    C --> D["Sprint Retrospective"]
    D --> E["Sprint kế tiếp"]
    E -. "Không có khoảng nghỉ bắt buộc giữa các Sprint" .-> A
~~~

Scrum Guide quy định các sự kiện này cùng mục đích của chúng; **không quy định mọi nhóm phải dùng cùng mẫu agenda, bảng tính, bộ ba câu hỏi hay công cụ phần mềm**.

## 3. Ba kiểu cuộc họp có vẻ giống nhau nhưng khác mục đích

Để không nhầm lẫn, hãy xem một cuộc họp theo **lý do tổ chức và quyền quyết định**, không chỉ theo tên trên lịch.

| Dạng tương tác | Câu hỏi chi phối | Tín hiệu đặc trưng | Vị trí trong Scrum |
| --- | --- | --- | --- |
| **Báo cáo tình trạng (status reporting)** | “Ai đã làm gì? Kịp kế hoạch chưa?” | Thông tin đi từ người thực hiện lên người giám sát | Có thể là nhu cầu quản trị khác, nhưng **không phải mục đích cốt lõi** của các Scrum event |
| **Phê duyệt hình thức (approval gate)** | “Ai được quyền ký cho phép đi tiếp?” | Tiến độ chờ chữ ký; có thể không phát hiện thêm điều gì | Có thể tồn tại do chính sách bắt buộc ở ngoài Scrum, nhưng **không được mặc định gắn với Sprint Review** |
| **Kiểm tra và thích ứng (inspection/adaptation)** | “Kết quả và bằng chứng nói gì? Cần điều chỉnh mục tiêu, kế hoạch hoặc cách làm thế nào?” | Mọi người nhìn cùng thực tế, trao đổi, chọn hành động | **Lý do tồn tại của Scrum event** |

Một sự kiện có thể chứa **thông tin về trạng thái**, nhưng **trạng thái là đầu vào để quyết định**, không phải đích đến. Tương tự, một nhóm có thể cần kiểm soát phát hành hoặc tuân thủ bắt buộc, nhưng không nên biến Sprint Review thành cuộc họp cấp dấu “cho phép làm việc” thay vì thảo luận giá trị và hướng đi.

### Ví dụ nhanh về cùng một câu chuyện

**Báo cáo:** “Story lưu tiến độ đã xong frontend 100%, backend 90%.”

**Kiểm tra:** “Học viên đã mở lại đúng vị trí đã lưu sau khi mạng mất chưa? Increment có đạt Definition of Done không?”

**Thích ứng:** “Bài kiểm thử cho thấy trạng thái lưu có thể sai. Chúng ta ưu tiên sửa lỗi xác nhận trước khi mở rộng tính năng thông báo và cập nhật Product Backlog theo rủi ro.”

Sự khác biệt nằm ở **đối tượng được xem xét và quyết định được rút ra**, không chỉ ở câu chữ.

## 4. Sprint: khung tạo giá trị, không phải chiếc hộp đóng băng mọi việc

Sprint là **nhịp làm việc cố định** giúp Scrum Team liên tục tiến gần Product Goal. Trong Sprint, nhóm xây dựng một hoặc nhiều Increment, học từ phản hồi và duy trì cơ hội điều chỉnh.

Trong thời gian Sprint:

- **Không thực hiện thay đổi làm nguy hại Sprint Goal.**
- **Chất lượng không giảm.** Definition of Done vẫn phải được đáp ứng cho Increment.
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ và **thương lượng với Product Owner** khi nhóm học thêm, miễn không làm mất Sprint Goal.

Không nên diễn giải Sprint thành “một hợp đồng cố định, mọi ticket đã chọn phải hoàn thành bất kể điều gì xảy ra”. Nếu quy tắc nghiệp vụ vừa phát hiện làm một story cần thay đổi, Developers và Product Owner cần trao đổi dựa trên mục tiêu chung.

### Sprint Goal là điểm tựa cho việc thích ứng

Ví dụ Sprint Goal của nền tảng học trực tuyến:

> Học viên đang học dở có thể quay lại đúng tiến độ đã được lưu thành công, với trạng thái rõ ràng khi việc lưu thất bại.

Nếu giữa Sprint phát hiện lỗi API lưu tiến độ, nhóm có cơ sở để ưu tiên giải quyết vì lỗi ấy **ảnh hưởng trực tiếp mục tiêu**. Ngược lại, một đề xuất đổi màu toàn bộ dashboard có thể được xem xét trong Product Backlog mà không chen ngay vào Sprint.

Trong Scrum, **chỉ Product Owner có quyền hủy Sprint**, và việc hủy phù hợp khi **Sprint Goal trở nên lỗi thời**. Đây không phải biện pháp để phản ứng với mọi story có nguy cơ chậm.

## 5. Sprint Planning: tạo mục tiêu và kế hoạch, không phải nhận lệnh giao việc

**Sprint Planning** khởi đầu Sprint bằng một công việc mang tính cộng tác của toàn Scrum Team. Theo Scrum Guide, cuộc trao đổi giải quyết ba chủ đề.

### 5.1. Chủ đề một — Vì sao Sprint này có giá trị?

**Product Owner** đề xuất cách sản phẩm có thể tăng giá trị và tính hữu ích trong Sprint. Toàn Scrum Team hợp tác xác định **Sprint Goal** — một mục tiêu duy nhất mang lại sự gắn kết cho công việc.

Ví dụ tốt:

> Người học mới có thể mở một bài đầu tiên phù hợp và nhìn thấy trạng thái tiến độ đã lưu một cách đáng tin cậy.

Ví dụ chưa tốt:

> Hoàn thành ticket 23, 24, 25 và 30; đạt 32 story point.

Ví dụ sau chỉ là danh sách output và số lượng, chưa trả lời vì sao Sprint có giá trị với sản phẩm. Nếu ticket 25 được chia hoặc cách hiện thực thay đổi, nhóm không biết điều gì thực sự cần bảo vệ.

### 5.2. Chủ đề hai — Có thể hoàn thành những gì trong Sprint?

Qua trao đổi với Product Owner, **Developers chọn Product Backlog Item** cho Sprint. Việc lựa chọn dựa trên mục tiêu, kinh nghiệm trước đây, năng lực hiện tại và mức độ hiểu biết về những hạng mục cần làm.

Sprint Planning không phải thời điểm Product Owner hoặc Scrum Master “chốt số điểm” rồi bắt Developers cam kết hoàn thành tất cả. **Story point là công cụ tùy chọn**, không thay thế việc đánh giá năng lực và rủi ro thực tế.

### 5.3. Chủ đề ba — Công việc đã chọn sẽ được thực hiện thế nào?

Developers lập kế hoạch công việc cần thiết để tạo Increment đáp ứng Definition of Done. Kế hoạch đủ chi tiết để nhóm bắt đầu và sẽ được cập nhật khi có thêm thông tin. Scrum Guide mô tả Developers thường phân tách PBI thành phần nhỏ hơn, trong một ngày hoặc ít hơn, nhưng cách lập kế hoạch thuộc về Developers.

**Sprint Backlog** gồm **Sprint Goal (vì sao), tập các PBI được chọn (cái gì) và kế hoạch thực hiện (làm thế nào)**. Đây là kế hoạch do và dành cho Developers, không phải bảng giao task từ cấp trên.

### Sprint Planning nên kết thúc với điều gì?

| Đầu ra hữu ích | Để làm gì? |
| --- | --- |
| **Sprint Goal rõ** | Giữ đội tập trung khi phát sinh thay đổi |
| **Các PBI được chọn** | Xác định phạm vi khởi đầu dựa trên năng lực và giá trị |
| **Kế hoạch khả thi của Developers** | Cho phép nhóm bắt đầu, phối hợp và điều chỉnh |
| **Bất định và phụ thuộc được nhìn thấy** | Không nhầm một kế hoạch chưa được kiểm chứng với sự chắc chắn |

**Dấu hiệu biến dạng:** Scrum Master chia việc cho từng người theo lịch; Product Owner cam kết một ngày chính xác thay nhóm; cuộc họp chỉ để mọi người ký vào danh sách tính năng không thể thay đổi.

## 6. Daily Scrum: Developers điều chỉnh kế hoạch, không báo cáo cho Scrum Master

**Daily Scrum** là sự kiện 15 phút dành cho **Developers của Scrum Team**. Mục đích là **kiểm tra tiến độ hướng tới Sprint Goal và thích ứng Sprint Backlog khi cần**, tạo một kế hoạch khả thi cho ngày làm việc tiếp theo.

**Không có định dạng ba câu hỏi bắt buộc**. Developers có thể dùng bảng công việc, xem luồng từ phải sang trái (việc gần hoàn thành trước), tập trung vào rủi ro Sprint Goal hoặc cách khác miễn đạt mục đích.

### Tình huống chưa đúng mục đích

Scrum Master lần lượt hỏi từng người:

> “Hôm qua em làm gì? Hôm nay em làm gì? Em có blocker không?”

Mọi người nhìn Scrum Master để trả lời; sau 15 phút không ai hỏi API tiến độ đang chặn giao diện, kiểm thử mất mạng cần ai phối hợp hoặc Sprint Goal có nguy cơ bị ảnh hưởng thế nào.

Ba câu hỏi trên **có thể hữu ích nếu Developers tự chọn chúng**, nhưng không nên biến Daily Scrum thành mẫu báo cáo bắt buộc để chấm công hoặc giám sát cá nhân.

### Cùng tình huống, theo đúng mục đích

Các Developers cùng xem Sprint Backlog:

> Developer A: “Muốn đạt Sprint Goal, luồng khôi phục tiến độ phải đạt DoD. Hiện giao diện báo lưu thành công khi API chưa xác nhận.”
>
> Developer B: “Tôi sẽ làm cặp với A để kiểm tra trạng thái API ngay sau Daily; chúng ta tạm ngừng story dashboard chưa liên quan.”
>
> Developer C: “Tôi bổ sung kiểm thử trường hợp mạng đứt trước xác nhận. Chiều nay cả nhóm xem Increment tích hợp.”

Kết quả: **kế hoạch thay đổi để tiến gần Sprint Goal**, không đơn thuần có thêm thông tin báo cáo.

### Những nguyên tắc giúp Daily Scrum hữu ích

1. Bắt đầu từ **Sprint Goal và công việc còn cần hoàn tất**, không từ danh sách hoạt động cá nhân.
2. Làm nổi các hạng mục bị chặn, phụ thuộc, lỗi chất lượng và quyết định cần trao đổi.
3. Chọn phối hợp sau Daily khi một vấn đề cần trao đổi kỹ thuật sâu; không biến 15 phút thành buổi thiết kế dài.
4. Để Developers tự sở hữu cách tổ chức, cập nhật Sprint Backlog và kế hoạch.
5. Scrum Master hỗ trợ huấn luyện khi cần, **không phải người bắt buộc điều khiển hoặc tham dự Daily Scrum**.

Nếu Product Owner hoặc Scrum Master đang **chủ động làm việc trên các hạng mục thuộc Sprint Backlog**, họ tham gia Daily Scrum với tư cách Developers theo Scrum Guide. Điều này khác với việc tham gia để nghe cấp dưới báo cáo.

## 7. Sprint Review: cùng xem sản phẩm và tương lai, không phải cửa phê duyệt phát hành

**Sprint Review** nhằm **kiểm tra kết quả Sprint và xác định các thích ứng trong tương lai**. Scrum Team trình bày kết quả công việc cho **stakeholder chủ chốt**, cùng thảo luận tiến triển hướng tới Product Goal và những thay đổi trong môi trường sản phẩm.

Scrum Guide nhấn mạnh đây là **một phiên làm việc, không chỉ là buổi thuyết trình**. Product Backlog có thể được điều chỉnh để phản ánh những cơ hội mới hoặc thay đổi dự định.

### Sprint Review khác bản demo thông thường thế nào?

Một demo có thể là thành phần hữu ích của Sprint Review; tuy nhiên chỉ mở màn hình rồi nhận lời khen không đủ tạo ra sự kiểm tra và thích ứng.

| Buổi trình diễn hình thức | Sprint Review hướng thực nghiệm |
| --- | --- |
| Nhóm nói đã hoàn thành bao nhiêu ticket | Nhóm và stakeholder xem **Increment thực tế** cùng mục tiêu sản phẩm |
| Chỉ trình bày những kịch bản đẹp nhất | Thảo luận hành vi, kết quả thử, giới hạn, rủi ro và điều chưa biết |
| Stakeholder chỉ nói “đồng ý” hoặc “không đồng ý” | Stakeholder phản hồi nhu cầu, bối cảnh, cơ hội và giá trị |
| Cuối buổi xin chữ ký “nghiệm thu Sprint” | Cuối buổi có hiểu biết mới để **thích ứng Product Backlog và hướng phát triển** |
| Không có thay đổi sau cuộc họp | Có quyết định hoặc bước kiểm chứng tiếp theo phù hợp |

### Sprint Review không phải điều kiện bắt buộc để phát hành

Một **Increment đáp ứng Definition of Done** có thể được chuyển giao cho stakeholder **trước khi Sprint kết thúc**. Sprint Review **không phải cổng phê duyệt để được phát hành giá trị**. Nhóm không nên trì hoãn phản hồi chỉ để đợi đến cuối Sprint.

Ngược lại, một hạng mục chưa đạt Definition of Done **không được xem là Increment hoàn thành** dù stakeholder có ký đồng ý. Nhóm có thể minh bạch trao đổi về phần chưa xong và ý tưởng cần học, nhưng không dùng Review để hợp thức hóa chất lượng còn thiếu.

### Ví dụ Review về tính năng lưu tiến độ

Scrum Team cho stakeholder thử:

1. Học viên mở bài, hoàn thành hai bước và thấy trạng thái đã lưu.
2. Học viên tải lại trang, được đưa về đúng vị trí.
3. Khi mạng bị ngắt trước xác nhận, giao diện không khẳng định đã lưu thành công.
4. Nhóm giới thiệu số liệu thử nghiệm và phản hồi hỗ trợ ban đầu, nêu rõ quy mô quan sát.

Một đại diện học viên phản ánh: “Tôi không biết nút ‘Thử lại’ có làm mất phần đã hoàn thành không.” Nhóm có thể quyết định làm rõ thông điệp hoặc thiết kế phép thử khả dụng; Product Owner cân nhắc sắp thứ tự hạng mục liên quan.

**Điều tạo giá trị ở Review không phải lời khen, mà là thay đổi hiểu biết và lựa chọn dựa trên Increment cùng phản hồi.**

## 8. Phân biệt Sprint Review với nghiệm thu, kiểm thử và phê duyệt tuân thủ

“Không phải cửa phê duyệt” **không đồng nghĩa** Scrum cho phép bỏ quy tắc bảo mật, pháp lý, chất lượng hoặc kiểm soát phát hành. Các hoạt động này có mục tiêu riêng và có thể cần thực hiện ở những thời điểm thích hợp.

| Hoạt động | Câu hỏi trọng tâm | Quan hệ với Scrum Review |
| --- | --- | --- |
| **Acceptance testing / tiêu chí chấp nhận** | Hạng mục có thể hiện đúng hành vi nghiệp vụ đã thống nhất không? | Cung cấp bằng chứng chất lượng; không thay Review về giá trị và hướng đi |
| **Definition of Done** | Increment có đạt tiêu chuẩn chất lượng để được coi là hoàn thành không? | Là commitment gắn với Increment, **không phải chữ ký trong Review** |
| **Phê duyệt phát hành theo chính sách** | Việc đưa thay đổi vào môi trường có tuân thủ quyền, an toàn, pháp lý và quy trình cần thiết không? | Có thể là kiểm soát riêng, không phải mục đích chính thức của Review |
| **Sprint Review** | Kết quả Sprint và bối cảnh sản phẩm nói gì; nên thích ứng điều gì tiếp? | Là event Scrum tạo cơ hội kiểm tra và thích ứng |
| **Nghiệm thu hợp đồng** | Những nghĩa vụ hoặc điều khoản giao nhận đã được đáp ứng chưa? | Có thể cần quy trình riêng; không nên đồng nhất với Sprint Review |

Ví dụ ứng dụng có dữ liệu học viên nhạy cảm có thể cần kiểm tra quyền truy cập trước khi phát hành. Scrum Team phải bảo đảm các điều kiện bắt buộc, nhưng có thể **tích hợp các kiểm soát vào công việc và Definition of Done phù hợp**, hoặc thực hiện quy trình phát hành riêng theo tổ chức. Không cần biến toàn bộ Sprint Review thành buổi ký giấy chỉ vì có những kiểm soát đó.

**Lưu ý:** Việc được phát hành và việc đã xác nhận outcome cũng khác nhau. Một tính năng hoàn thành đúng và được phát hành an toàn vẫn có thể không giải quyết vấn đề người dùng như giả định; Sprint Review và phản hồi tiếp theo giúp nhóm học điều này.

## 9. Sprint Retrospective: cải tiến cách làm, không phải buổi tìm người chịu lỗi

**Sprint Retrospective** có mục đích **lập kế hoạch nâng cao chất lượng và hiệu quả**. Scrum Team kiểm tra Sprint vừa qua về con người, tương tác, quy trình, công cụ và Definition of Done; xem điều gì thuận lợi hoặc không, tìm nguyên nhân giả định, rồi xác định các thay đổi có ích.

Đây là **sự kiện kết thúc Sprint**. Retrospective tập trung vào **cách Scrum Team làm việc và tạo ra chất lượng**, khác với Sprint Review tập trung vào **kết quả sản phẩm và hướng đi**.

### Phân biệt Review và Retrospective

| Câu hỏi | Sprint Review | Sprint Retrospective |
| --- | --- | --- |
| Trọng tâm | Increment, Product Goal, bối cảnh thị trường/người dùng, Product Backlog | Chất lượng, hiệu quả, phối hợp, quy trình và công cụ |
| Thành phần | Scrum Team và stakeholder chủ chốt | Scrum Team |
| Dữ liệu đầu vào | Phần mềm hoạt động, kết quả dùng thử, thay đổi nhu cầu, rủi ro sản phẩm | Thời gian chờ, lỗi tích hợp, cách phối hợp, chất lượng, khó khăn nhóm |
| Thích ứng điển hình | Sắp thứ tự backlog, điều chỉnh giả thuyết và hướng sản phẩm | Cải tiến thực hành làm việc, loại bỏ trở ngại, nâng Definition of Done khi cần |
| Không nên biến thành | Buổi xin duyệt cho phép giao hàng | Buổi chỉ trích cá nhân hoặc tổng hợp lời phàn nàn không hành động |

### Một Retrospective chưa hữu ích

> “Sprint này ai cũng bận. Lần sau cần phối hợp tốt hơn. Cảm ơn mọi người.”

Không có vấn đề được xác định cụ thể, nguyên nhân chưa được thảo luận, không có thử nghiệm và cũng không có cách đánh giá “tốt hơn” nghĩa là gì.

### Một Retrospective có thể tạo thay đổi

Nhóm thấy bốn PBI bị chờ kiểm thử tích hợp vào hai ngày cuối Sprint. Qua thảo luận, mọi người phát hiện các PBI được chia theo frontend/backend thay vì theo luồng dùng được; Developers thường mở việc mới khi phần đang làm chưa xong.

Một thử nghiệm:

> “Trong Sprint kế tiếp, nhóm chọn một hoặc hai lát cắt end-to-end trước; khi có hạng mục bị chặn ở kiểm thử, ưu tiên phối hợp hoàn tất thay vì mở thêm hạng mục. Theo dõi WIP và thời gian chờ kiểm thử, cùng lỗi sau bàn giao.”

Nhóm thống nhất ai theo dõi tín hiệu và xem lại ở Retrospective tiếp theo. Scrum Master hỗ trợ cuộc trao đổi, nhưng **cả Scrum Team sở hữu việc cải tiến**.

### Tránh phạt người nói ra vấn đề

Nếu việc nêu lỗi bị dùng để đánh giá hoặc quy trách nhiệm cá nhân một cách thiếu công bằng, thành viên có thể che giấu rủi ro. Retrospective cần **tôn trọng, cởi mở và dũng cảm** để nhóm hiểu vấn đề thật. Điều đó không có nghĩa bỏ qua trách nhiệm khi có sai phạm nghiêm trọng; những vấn đề này phải được giải quyết theo cơ chế phù hợp, không biến toàn bộ Retro thành buổi xét lỗi.

## 10. Các event liên kết với artifact và commitment như thế nào?

Ba artifact của Scrum cùng commitment:

| Artifact | Commitment | Câu hỏi giữ nhóm tập trung |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Sản phẩm đang hướng tới trạng thái giá trị nào? |
| **Sprint Backlog** | **Sprint Goal** | Trong Sprint này, bước tiến có ý nghĩa là gì? |
| **Increment** | **Definition of Done** | Phần sản phẩm có thực sự hoàn thành theo tiêu chuẩn chất lượng không? |

Những cam kết này tạo **trọng tâm và sự minh bạch** để kiểm tra và thích ứng có ý nghĩa.

~~~mermaid
flowchart TD
    PG["Product Goal + Product Backlog"] --> SP["Sprint Planning: chọn Sprint Goal, PBI, kế hoạch"]
    SP --> SB["Sprint Goal + Sprint Backlog"]
    SB --> DS["Daily Scrum: kiểm tra mục tiêu, thích ứng kế hoạch"]
    DS --> INC["Increment đáp ứng Definition of Done"]
    INC --> SR["Sprint Review: kiểm tra sản phẩm và bối cảnh"]
    SR --> PG
    DS --> RT["Sprint Retrospective: cải tiến chất lượng và hiệu quả"]
    RT --> SP
~~~

Sơ đồ thể hiện dòng học hỏi, không phải thứ tự máy móc cho mọi hoạt động. Trong Sprint, có thể có **nhiều Increment**, có thể được phát hành sớm; Product Backlog có thể được làm rõ liên tục; Developers có thể điều chỉnh kế hoạch khi cần mà không chờ Daily Scrum.

### Vì sao “ký Done trong Review” là sai ngữ nghĩa?

Definition of Done là mô tả chính thức về trạng thái Increment khi đáp ứng những tiêu chuẩn chất lượng đã yêu cầu. **Một Product Backlog Item chưa đạt Definition of Done không được tính là một phần của Increment hoàn thành** và không nên được trình bày như đã hoàn tất chỉ vì stakeholder đồng ý.

Ngược lại, Scrum Team không cần chờ đến Review mới được tạo thêm Increment hoặc nhận phản hồi. Khả năng giao giá trị **tăng dần, liên tục** mới là một lợi ích quan trọng của cách làm Agile.

## 11. Tình huống xuyên suốt: cùng một Sprint nhưng hai cách tổ chức

**Bối cảnh giả định:** Nền tảng học trực tuyến muốn giảm tình trạng học viên phải học lại vì tiến độ lưu không đáng tin khi mạng chập chờn. Scrum Team gồm Product Owner, Developers và Scrum Master. Product Goal là **người học tự bắt đầu và tiếp tục khóa học một cách đáng tin cậy**.

### 11.1. Cách vận hành theo nghi thức báo cáo

| Thời điểm | Điều nhóm đang làm | Vấn đề |
| --- | --- | --- |
| Sprint Planning | Quản lý đưa danh sách 25 ticket, giao từng người và yêu cầu cam kết làm hết | Không có Sprint Goal có ý nghĩa; Developers không sở hữu kế hoạch |
| Daily Scrum | Từng người đọc giờ làm và phần trăm hoàn thành cho Scrum Master | Không phát hiện sớm rủi ro tích hợp và dữ liệu |
| Sprint Review | Trình chiếu màn hình mới và xin stakeholder ký “hoàn thành” | Không quan sát người dùng thử; chất lượng bị đồng nhất với chữ ký |
| Sprint Retrospective | Nói “cần tích cực hơn” rồi kết thúc | Không có cải tiến có thể kiểm chứng |
| Trong Sprint | Việc mới chen vào qua tin nhắn cá nhân | Thứ tự thiếu minh bạch, kế hoạch mất trọng tâm |

Kết quả có thể là nhiều ticket đóng nhưng lỗi mất tiến độ vẫn còn. **Đó là ví dụ giả định cho phản mẫu, không phải dữ liệu thực tế về một sản phẩm cụ thể.**

### 11.2. Cách vận hành hướng tới kiểm tra và thích ứng

**Sprint Planning:** Product Owner nêu vấn đề và bằng chứng: một số học viên thấy thông báo lưu thành công nhưng khi quay lại không tìm thấy tiến độ. Scrum Team tạo Sprint Goal:

> “Học viên trên bản web thí điểm có thể quay lại đúng tiến độ đã lưu thành công và nhận thông báo trung thực khi việc lưu thất bại.”

Developers cùng chọn các PBI có thể thực hiện, làm rõ quy tắc “đã lưu”, chia lát cắt từ giao diện đến API và kiểm thử, nhận diện phụ thuộc vào dịch vụ tiến độ.

**Daily Scrum:** Nhóm kiểm tra luồng đạt Sprint Goal. Ngày thứ ba phát hiện API phản hồi chậm và đôi khi trả trạng thái không nhất quán. Developers điều chỉnh kế hoạch: hai người tập trung kiểm thử và sửa luồng xác nhận, tạm ngừng mở chức năng hiển thị không liên quan.

**Trong Sprint:** Sau khi sửa lỗi và đáp ứng Definition of Done, nhóm đưa Increment đến môi trường thí điểm phù hợp theo chính sách phát hành; quan sát dữ liệu kỹ thuật và trải nghiệm thử, không phải đợi ngày Review mới được có phản hồi.

**Sprint Review:** Scrum Team và stakeholder thao tác luồng học dở, tải lại và mất mạng; xem tỷ lệ lưu thành công và những hạn chế đã biết. Đại diện học viên cho rằng thông báo “đang đồng bộ” cần rõ hơn. Product Owner xem xét hạng mục cải thiện thông điệp trong Product Backlog và cân nhắc mức ưu tiên so với các vấn đề khác.

**Sprint Retrospective:** Nhóm nhận thấy phần lớn thời gian bị mất vì kiểm thử tích hợp chỉ được thực hiện cuối Sprint. Họ thống nhất thử chạy kiểm thử tự động sau các thay đổi nhỏ và bắt đầu sớm từ một lát cắt end-to-end, rồi đo thời gian chờ và số lỗi tích hợp trong Sprint tiếp.

### 11.3. Một vòng giá trị hoàn chỉnh

~~~text
Product Goal:
  Học viên tiếp tục học đáng tin cậy.

Sprint Goal:
  Khôi phục đúng tiến độ đã lưu và hiển thị trung thực khi lưu thất bại.

Sprint Planning:
  Chọn phạm vi và kế hoạch khả thi để đạt Sprint Goal.

Daily Scrum:
  Kiểm tra tiến độ tới mục tiêu; đổi cách phối hợp khi API gặp rủi ro.

Increment đạt DoD:
  Luồng lưu/khôi phục đúng trong phạm vi đã thống nhất.

Sprint Review:
  Stakeholder thử và cung cấp phản hồi về trải nghiệm, dữ liệu và giá trị.

Sprint Retrospective:
  Cải tiến cách tích hợp, kiểm thử và phối hợp.

Kỳ tiếp theo:
  Product Backlog và cách làm được điều chỉnh bằng điều đã học.
~~~

Điều đáng chú ý là **cả sản phẩm và cách làm đều được thích ứng**, không chỉ những con số báo cáo thay đổi.

## 12. Ai sở hữu quyết định ở từng event?

Những sự kiện Scrum có thể được tạo điều kiện bởi Scrum Master, nhưng trách nhiệm quyết định **không chuyển sang Scrum Master chỉ vì họ điều hành cuộc họp**.

| Vấn đề | Accountability chính | Vai trò hỗ trợ |
| --- | --- | --- |
| Nêu định hướng giá trị và sắp thứ tự Product Backlog | **Product Owner** | Developers, Scrum Master và stakeholder cung cấp thông tin |
| Cùng tạo Sprint Goal tại Sprint Planning | **Scrum Team** | Product Owner đề xuất giá trị; cả nhóm cộng tác |
| Chọn công việc phù hợp năng lực và lập kế hoạch thực hiện trong Sprint | **Developers**, qua thảo luận với Product Owner | Scrum Master huấn luyện nếu cần |
| Kiểm tra tiến độ hướng tới Sprint Goal tại Daily Scrum và điều chỉnh Sprint Backlog | **Developers** | Scrum Master bảo đảm hiểu mục đích, không biến thành báo cáo |
| Kiểm tra Increment và môi trường sản phẩm trong Review | **Scrum Team cùng stakeholder** | Product Owner chịu trách nhiệm quyết định backlog; Scrum Master hỗ trợ phối hợp |
| Chọn cải tiến chất lượng và hiệu quả tại Retrospective | **Scrum Team** | Scrum Master hỗ trợ trao đổi và tháo gỡ rào cản |
| Hủy Sprint nếu Sprint Goal lỗi thời | **Product Owner** | Cân nhắc cùng Scrum Team và stakeholder theo tình hình |

Scrum Team là một đội **tự quản lý và liên chức năng**. Trong tổ chức có thể tồn tại quyền pháp lý, bảo mật, nhân sự hoặc vận hành khác; cần phối hợp đúng thẩm quyền mà không biến các event thành đường vòng để một cá nhân tự ý thay trách nhiệm của nhóm.

## 13. Cách điều phối để sự kiện không bị biến thành biểu diễn

Scrum Master chịu trách nhiệm về hiệu quả Scrum Team và giúp mọi người hiểu Scrum. Scrum Guide nêu Scrum Master bảo đảm Scrum events diễn ra, mang tính tích cực, hiệu quả và nằm trong timebox. Điều này **không yêu cầu Scrum Master trực tiếp điều phối tất cả event**.

### Trước sự kiện

- Làm rõ **mục đích**: kiểm tra điều gì, câu hỏi quyết định nào cần trả lời?
- Chuẩn bị **bằng chứng phù hợp**: Product Backlog, Sprint Goal, Increment có thể thử, kết quả kiểm thử, tín hiệu người dùng hoặc dữ liệu dòng công việc.
- Mời đúng người; đặc biệt Sprint Review cần stakeholder có góc nhìn liên quan.
- Đưa những bất định quan trọng ra trước, tránh để cuộc họp chỉ còn đọc slide.

### Trong sự kiện

- Giữ trọng tâm vào **mục đích**, không chỉ vào việc mọi người đã phát biểu đủ lượt.
- Khuyến khích những ý kiến khác nhau được nêu dựa trên ví dụ và bằng chứng.
- Tách thông tin quan sát khỏi suy đoán; ghi rõ vấn đề nào cần kiểm chứng thêm.
- Tránh chiếm quyền quyết định của Product Owner hoặc Developers.
- Điều phối cuộc trao đổi sâu ngoài timebox khi cần mà không kéo dài toàn bộ event vô hạn.

### Sau sự kiện

- Xác định điều đã thay đổi: kế hoạch, thứ tự backlog, thử nghiệm cải tiến hoặc câu hỏi cần tìm hiểu.
- Giữ **người chịu trách nhiệm và điểm xem lại** rõ ràng khi có công việc tiếp theo.
- Không tạo thêm biên bản dài nếu một cập nhật minh bạch trong artifact là đủ.
- Quan sát xem quyết định có được thực hiện và tạo tác dụng hay không.

**Không nên định nghĩa thành công bằng “đã đủ người tham dự và đúng 15 phút”**. Thành công nằm ở việc sự kiện tạo được kiểm tra và thích ứng tương xứng với mục đích.

## 14. Đo hiệu quả sự kiện bằng học hỏi và kết quả, không chỉ số buổi họp

| Tín hiệu | Có thể nói gì? | Giới hạn diễn giải |
| --- | --- | --- |
| **Sprint Goal rõ và được dùng khi quyết định** | Planning và Daily có giúp tạo trọng tâm không? | Không phải mọi Sprint đều đạt trọn mục tiêu; cần xem bối cảnh |
| **Thời gian tới phản hồi** | Review và bàn giao Increment có giúp học sớm không? | Phản hồi nhanh nhưng mẫu quá nhỏ vẫn có thể sai lệch |
| **Cycle time / WIP** | Dòng công việc có bị tắc hoặc mở quá nhiều việc không? | Giảm thời gian bằng bỏ kiểm thử là tác động xấu |
| **Số lỗi tích hợp và chất lượng Increment** | Nhóm có giữ DoD và kiểm thử xuyên Sprint không? | Chỉ đếm số lỗi có thể bỏ qua độ nghiêm trọng |
| **Số cải tiến Retro được thử và xem lại** | Retrospective có dẫn đến hành động không? | Chạy nhiều thử nghiệm không có nghĩa cải tiến hiệu quả |
| **Độ rõ của Product Backlog sau Review** | Phản hồi stakeholder có hỗ trợ Product Owner quyết định không? | Backlog dài/ngắn chưa trực tiếp cho biết chất lượng quyết định |
| **Outcome người dùng và chỉ số bảo vệ** | Increment có tạo giá trị mà vẫn an toàn không? | Không quy toàn bộ biến động cho một sự kiện hoặc một cá nhân |

Ví dụ nhóm trước đây chờ **ba ngày** để kiểm thử tích hợp sau khi viết mã. Sau khi thay đổi cách phối hợp từ Retrospective, nhiều hạng mục được kiểm tra tích hợp sớm hơn; đồng thời tỷ lệ lỗi sau phát hành không tăng. Đây là tín hiệu cần tiếp tục quan sát để đánh giá cải tiến. **Các con số trong ví dụ là giả định**, không phải bằng chứng đã đo.

Không nên dùng sự kiện như nơi **xếp hạng Developers theo story point, số giờ làm hoặc số lần phát biểu**. Cách dùng đó có thể khiến mọi người che giấu rủi ro và làm giảm minh bạch.

## 15. Kết hợp Kanban và XP mà không làm mất mục đích Scrum event

Scrum là framework; nhóm có thể bổ sung phương pháp giúp xây Increment chất lượng và rút ngắn phản hồi.

### Kanban hỗ trợ nhìn luồng công việc

Trong Daily Scrum, Developers có thể xem bảng công việc:

~~~text
Sẵn sàng → Đang làm → Chờ review → Kiểm thử tích hợp → Đạt DoD
                ↑             ↑
        WIP vượt giới hạn?   Bị chặn bao lâu?
~~~

Các câu hỏi về **WIP, thời gian chờ, công việc gần hoàn tất và phụ thuộc** giúp nhóm điều chỉnh kế hoạch. Nhưng bảng Kanban không thay mục đích Daily Scrum bằng việc lần lượt đọc trạng thái từng thẻ.

### XP hỗ trợ phản hồi kỹ thuật trước cả Review

Các thực hành **TDD, lập trình cặp, tích hợp liên tục và tái cấu trúc** trong Extreme Programming giúp phát hiện sai sót khi phần mềm thay đổi. Nhóm không nên chờ tới Sprint Review mới biết bản build không chạy hoặc tiến độ không lưu.

Những dữ liệu kỹ thuật đó làm **Sprint Review có ý nghĩa hơn**, vì Scrum Team có Increment đáng tin để thảo luận giá trị thay vì chỉ thảo luận việc đã viết bao nhiêu mã.

### Các cuộc trao đổi bổ sung không phải Scrum event

Refinement, workshop nghiệp vụ, phiên thử khả dụng, họp xử lý sự cố hoặc làm việc cùng stakeholder có thể rất hữu ích. Nhưng **Product Backlog refinement không được liệt kê là một Scrum event chính thức** trong Scrum Guide 2020. Việc phân biệt tên gọi giúp mọi người không nhầm một hoạt động bổ trợ với cam kết về các event cốt lõi.

## 16. Những phản mẫu phổ biến và cách sửa

| Phản mẫu | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Planning là buổi giao việc** | Developers không sở hữu kế hoạch; mục tiêu mờ | Toàn Scrum Team tạo Sprint Goal, Developers chọn và lập kế hoạch |
| **Sprint Goal là tổng ticket/story point** | Khó thích ứng khi phạm vi thay đổi | Viết mục tiêu theo khả năng tạo giá trị có thể kiểm chứng |
| **Daily là báo cáo cho Scrum Master** | Không điều chỉnh kế hoạch, lỗi tích hợp phát hiện muộn | Developers kiểm tra tiến độ tới Sprint Goal và chủ động phối hợp |
| **Daily bắt buộc đọc ba câu hỏi** | Làm theo mẫu nhưng không bàn trở ngại thực | Cho Developers chọn cấu trúc phù hợp mục đích |
| **Review là buổi trình diễn đẹp mắt** | Không học từ sản phẩm hoặc nhu cầu thật | Cho stakeholder xem và tương tác với Increment, trao đổi bối cảnh |
| **Review là buổi ký duyệt phát hành** | Phản hồi và chuyển giao giá trị bị chậm | Tách kiểm soát phát hành bắt buộc khỏi mục đích Review |
| **Review chấp nhận cả việc chưa đạt DoD** | Mất minh bạch chất lượng, nợ kỹ thuật tăng | Phân biệt PBI chưa hoàn tất với Increment đã đạt DoD |
| **Retrospective là buổi đổ lỗi** | Thành viên che giấu vấn đề, mất niềm tin | Xem hệ thống làm việc, tạo môi trường tôn trọng và an toàn để nói thật |
| **Retrospective không có thử nghiệm** | Vấn đề lặp lại qua nhiều Sprint | Chọn cải tiến nhỏ, quan sát kết quả và xem lại |
| **Chỉ kiểm tra phần trăm hoàn thành** | Không thấy giá trị thực, công việc dở hoặc rủi ro | Kiểm tra Increment, outcome, DoD và thời gian tới phản hồi |
| **Bắt mọi quyết định chờ đến event kế tiếp** | Phản hồi và xử lý trở ngại chậm không cần thiết | Trao đổi khi cần trong Sprint; event là cơ hội chính thức, không phải cơ hội duy nhất |
| **Thêm nhiều cuộc họp để “báo cáo Scrum”** | Tốn thời gian, tạo nhiều nguồn sự thật | Dùng artifact minh bạch và đặt mục đích rõ cho mỗi buổi trao đổi |

## 17. Bài thực hành: chuyển một lịch họp hình thức thành Scrum hữu ích

**Bối cảnh giả định:** Một Scrum Team phát triển nền tảng học trực tuyến. Vấn đề là người học khó tiếp tục từ tiến độ đã lưu sau khi mất mạng; Sprint dự kiến dài hai tuần.

### Bài 1 — Nhận diện mục đích thật của cuộc họp

Với từng câu dưới đây, xác định **event phù hợp**, **điều đang bị hiểu sai** và **cách chuyển sang kiểm tra/thích ứng**.

| Phát biểu đang diễn ra | Cần thảo luận |
| --- | --- |
| “Họp Planning để giám đốc giao 20 ticket cho Developers.” | Ai cùng tạo Sprint Goal? Ai chọn PBI và lập kế hoạch? |
| “Hằng ngày, mọi người báo số giờ cho Scrum Master.” | Developers cần điều chỉnh gì để tiến gần Sprint Goal? |
| “Cuối Sprint chỉ cần khách hàng ký vào slide là Done.” | Increment đạt DoD chưa? Review cần kiểm tra giá trị và bối cảnh gì? |
| “Retro chỉ cần hỏi ai làm chậm Sprint.” | Có thể kiểm tra rào cản hệ thống và thử cải tiến gì? |
| “Nếu Review chưa diễn ra thì không được phát hành.” | Điều kiện phát hành thực sự là gì? Có phải do Scrum quy định không? |

### Bài 2 — Soạn Sprint Goal và cách kiểm tra

Viết một Sprint Goal cho vấn đề lưu tiến độ.

**Đáp án mẫu:**

> “Học viên trên bản web thí điểm có thể tiếp tục bài từ tiến độ đã được lưu thành công và nhận biết khi tiến độ chưa được đồng bộ.”

Hãy viết ba câu hỏi dành cho Daily Scrum dựa trên mục tiêu này:

1. Luồng lưu và khôi phục còn phần nào ngăn đạt Definition of Done?
2. Có lỗi hoặc phụ thuộc nào cần phối hợp hôm nay thay vì mở thêm việc?
3. Developers cần đổi kế hoạch theo cách nào để hoàn thành lát cắt có giá trị?

Đây là **câu hỏi gợi ý**, không phải ba câu bắt buộc của Scrum Guide.

### Bài 3 — Thiết kế Sprint Review có tương tác

Hãy chuẩn bị:

- Một **Increment đáp ứng DoD** để người tham gia thử trực tiếp.
- Hai tình huống: lưu/khôi phục thành công và mất mạng trước khi lưu hoàn tất.
- Một tín hiệu từ người dùng hoặc hỗ trợ học viên, kèm giới hạn của bằng chứng.
- Ba câu hỏi về kết quả sản phẩm: “Người học hiểu trạng thái chưa?”, “Điều nào còn gây nhầm lẫn?”, “Có thay đổi nào về nhu cầu hoặc rủi ro?”
- Phương án để Product Owner ghi quyết định hoặc thay đổi thứ tự Product Backlog sau trao đổi.

**Yêu cầu thêm:** Chỉ ra một quyết định phát hành hoặc kiểm soát bảo mật có thể cần quy trình riêng, và giải thích vì sao nó **không phải mục đích chính của Sprint Review**.

### Bài 4 — Thiết kế thử nghiệm từ Retrospective

Quan sát: Bốn hạng mục phải chờ kiểm thử tích hợp từ một đến ba ngày vào cuối Sprint.

~~~text
Vấn đề:
  Kiểm thử tích hợp đến muộn làm kéo dài thời gian hoàn thành.

Giả thuyết:
  Nếu chọn lát cắt end-to-end và chạy kiểm thử tích hợp sớm,
  nhóm sẽ giảm thời gian chờ và phát hiện lỗi trước ngày cuối.

Thay đổi thử:
  Bắt đầu với một lát cắt nhỏ; Developers phối hợp kiểm thử
  theo từng thay đổi có thể tích hợp, thay vì đợi hết frontend/backend.

Tín hiệu:
  Thời gian chờ review/kiểm thử, WIP,
  lỗi tích hợp và khả năng đạt DoD.

Thời điểm xem lại:
  Retrospective cuối Sprint tiếp theo.
~~~

Hãy đánh giá xem thử nghiệm **giữ nguyên chất lượng** hay chỉ đẩy lỗi sang môi trường sử dụng.

### Bài 5 — Phân biệt đúng người quyết định

Trả lời nhanh:

1. **Ai** chịu trách nhiệm sắp thứ tự Product Backlog sau phản hồi Sprint Review?
2. **Ai** điều chỉnh Sprint Backlog và kế hoạch hằng ngày?
3. **Ai** giúp Scrum events diễn ra hữu ích và được hiểu đúng?
4. **Ai** cùng xây Sprint Goal?
5. **Ai** có quyền hủy Sprint khi Sprint Goal trở nên lỗi thời?

**Gợi ý:** (1) Product Owner; (2) Developers; (3) Scrum Master hỗ trợ Scrum được áp dụng đúng và hiệu quả; (4) Scrum Team; (5) Product Owner.

## 18. Checklist phân biệt sự kiện Scrum với nghi thức hình thức

- [ ] Mọi thành viên hiểu **Sprint là event bao trùm**, không chỉ là kỳ báo cáo.
- [ ] **Sprint Planning** trả lời *vì sao, cái gì, làm thế nào* với Sprint Goal rõ.
- [ ] **Developers** sở hữu kế hoạch Sprint; không chờ Scrum Master giao từng task.
- [ ] **Daily Scrum** kiểm tra tiến độ tới Sprint Goal và điều chỉnh Sprint Backlog, không báo cáo giờ cho quản lý.
- [ ] **Sprint Review** kiểm tra Increment, Product Goal và nhu cầu hiện tại cùng stakeholder.
- [ ] Review không bị biến thành **cửa phê duyệt bắt buộc để được phát hành**.
- [ ] Không coi hạng mục chưa đạt **Definition of Done** là Increment hoàn thành vì có chữ ký.
- [ ] **Sprint Retrospective** tạo một hoặc vài cải tiến cụ thể cho chất lượng và hiệu quả.
- [ ] Các event giữ **timebox**, nhưng không lấy thời lượng và tỷ lệ tham dự làm thước đo duy nhất.
- [ ] Phản hồi được chuyển thành **quyết định có người chịu trách nhiệm** phù hợp.
- [ ] Có thể trao đổi và thích ứng **trong Sprint** khi cần, không đợi tới event tiếp theo.
- [ ] Chỉ số dùng để học về giá trị và dòng công việc, không để giám sát hay so điểm cá nhân.

## 19. Câu hỏi ôn tập

1. Ba trụ cột thực nghiệm của Scrum là gì và liên quan đến các event thế nào?
2. Scrum có bao nhiêu event chính thức nếu tính cả Sprint? Bốn event bên trong Sprint là gì?
3. Sprint Planning trả lời những câu hỏi chính nào?
4. Vì sao Sprint Goal không nên chỉ là danh sách ticket hoặc tổng story point?
5. Daily Scrum phục vụ ai, và Scrum Guide có bắt buộc dùng ba câu hỏi “hôm qua/hôm nay/blocker” không?
6. Một cuộc Daily kết thúc đúng 15 phút nhưng không làm thay đổi hiểu biết hay kế hoạch có thể còn thiếu điều gì?
7. Sprint Review khác kiểm thử chấp nhận và phê duyệt phát hành thế nào?
8. Increment có thể được chuyển giao trước Sprint Review không? Điều kiện chất lượng là gì?
9. Sprint Retrospective tập trung vào vấn đề gì khác Sprint Review?
10. Scrum Master có bắt buộc phải chủ trì tất cả Scrum event không?
11. Ai chịu trách nhiệm sắp thứ tự Product Backlog, ai chịu trách nhiệm kế hoạch trong Sprint?
12. Khi yêu cầu thay đổi giữa Sprint, điều gì cần giữ ổn định và điều gì có thể được thương lượng?
13. Khi nào một kiểm soát tuân thủ riêng là hợp lý, và vì sao không nên gắn nó mặc định với Sprint Review?
14. Những tín hiệu nào giúp biết sự kiện đang hỗ trợ tạo **giá trị và phản hồi sớm**, thay vì chỉ tăng báo cáo?

**Ghi nhớ:** Scrum event không phải những cuộc họp được đổi tên. **Sprint Planning** tạo mục tiêu và kế hoạch khả thi; **Daily Scrum** giúp Developers kiểm tra tiến độ và thích ứng kế hoạch; **Sprint Review** kiểm tra kết quả sản phẩm cùng stakeholder để điều chỉnh hướng đi; **Sprint Retrospective** cải tiến chất lượng và hiệu quả làm việc. **Sprint** là nhịp bao trùm, tạo cơ hội liên tục xây Increment đạt Definition of Done và học hỏi. Báo cáo tình trạng có thể cung cấp thông tin và kiểm soát tuân thủ có thể cần thiết, nhưng **không được thay thế mục đích cốt lõi của các sự kiện: minh bạch, kiểm tra và thích ứng để tạo giá trị**.
