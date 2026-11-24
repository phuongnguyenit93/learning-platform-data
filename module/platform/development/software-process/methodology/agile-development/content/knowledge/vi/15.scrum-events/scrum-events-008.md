# Sự kiện Scrum: Giới hạn thời gian và tính nhất quán của nhịp sự kiện

Một nhóm phát triển ứng dụng đặt lịch có thể bắt đầu với ý định tốt: mỗi tuần họp khi có thời gian, Daily Scrum kéo dài đến khi mọi người báo cáo xong, Sprint Review bị dời vì chưa có gì để trình bày, và Sprint Retrospective thường bị bỏ khi sắp đến hạn phát hành. Sau vài vòng, nhóm phát hiện mình thường xuyên làm việc dựa trên thông tin cũ, lỗi chỉ được nhìn thấy ở cuối giai đoạn và các cải tiến đã thống nhất không bao giờ được kiểm tra lại.

**Scrum sử dụng các sự kiện có mục đích, giới hạn thời gian và nhịp lặp rõ ràng để tạo cơ hội kiểm tra và thích ứng.** Giới hạn thời gian (*timebox*) giúp nhóm tập trung vào kết quả cần đạt; tính nhất quán của nhịp sự kiện (*cadence*) giảm chi phí điều phối, tạo thời điểm thường xuyên để nhìn lại sản phẩm và cách làm việc. Cả hai đều phục vụ **minh bạch – kiểm tra – thích ứng**, không phải để tối đa hóa số giờ họp hay duy trì nghi thức hình thức.

Trong mô-đun **AGILE_DEVELOPMENT**, người học tìm hiểu cách giao phần mềm có giá trị theo từng phần, nhận phản hồi sớm, thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc. Bài này tập trung vào **giới hạn thời gian và nhịp tổ chức của các sự kiện Scrum**: hiểu quy định theo Scrum, thiết kế lịch thực hành phù hợp, xử lý gián đoạn, bảo vệ chất lượng và đánh giá hiệu quả của các vòng phản hồi.

## 1. Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích vai trò của **Sprint**, **Sprint Planning**, **Daily Scrum**, **Sprint Review** và **Sprint Retrospective** trong nhịp Scrum.
2. Nêu đúng giới hạn thời gian theo Scrum cho từng sự kiện và phân biệt **mức tối đa** với **khoảng thời gian phải dùng hết**.
3. Thiết kế lịch Sprint nhất quán, bao gồm Daily Scrum vào mỗi ngày làm việc, Review và Retrospective trước Sprint kế tiếp.
4. Kết nối mục tiêu sự kiện với **Product Goal, Sprint Goal, Product Backlog, Sprint Backlog, Increment** và **Definition of Done**.
5. Điều phối những cuộc trao đổi đúng trọng tâm, không biến Daily Scrum thành báo cáo trạng thái hoặc Sprint Review thành buổi trình diễn một chiều.
6. Đề xuất cách xử lý khi sự kiện bị kéo dài, người tham gia vắng mặt, có sự cố khẩn hoặc nhóm làm việc phân tán.
7. Kiểm tra liệu nhịp Scrum có giúp giao giá trị và cải tiến thật hay chỉ tạo thêm chi phí họp.
8. Thực hành một kế hoạch hai tuần, phân tích các phản ví dụ và xây checklist vận hành nhóm.

## 2. Vì sao Scrum cần nhịp sự kiện nhất quán?

Scrum là một khung làm việc nhẹ dựa trên **chủ nghĩa thực nghiệm**. Nhóm không thể biết chắc mọi nhu cầu và rủi ro ngay từ đầu; họ cần tạo phần mềm có thể kiểm tra, quan sát những gì đang xảy ra và điều chỉnh quyết định.

Một nhịp sự kiện ổn định giúp:

- **Tạo các điểm kiểm tra dự đoán được:** nhóm và stakeholder biết khi nào cùng xem tiến triển, sản phẩm và cách làm việc.
- **Rút ngắn thời gian phát hiện vấn đề:** công việc không rõ, thay đổi nhu cầu và cản trở được nhìn thấy trước khi trở thành bất ngờ lớn.
- **Giảm chi phí sắp lịch:** không cần thương lượng lại thời điểm họp mỗi ngày hoặc mỗi Sprint.
- **Bảo vệ thời gian tập trung:** sự kiện có mục đích và timebox giúp tránh thảo luận lan man.
- **Tạo cơ hội cải tiến liên tục:** nhóm quan sát kết quả rồi chọn thử thay đổi nhỏ ở vòng tiếp theo.
- **Giúp bên liên quan tham gia đúng lúc:** họ không phải đoán khi nào sẽ xem Increment hoặc cung cấp phản hồi.

Tuy nhiên, **nhịp đều không đồng nghĩa nhóm tạo giá trị**. Nếu mọi sự kiện diễn ra đúng giờ nhưng không có Increment đạt Definition of Done, không có phản hồi đáng tin hoặc không có quyết định thích ứng, Scrum đã trở thành lịch họp thay vì cơ chế học hỏi.

### 2.1. Mỗi sự kiện có một câu hỏi trung tâm

| Sự kiện | Câu hỏi trọng tâm | Kết quả mong muốn |
| --- | --- | --- |
| **Sprint** | Trong một khoảng ngắn cố định, nhóm có thể tiến gần Product Goal bằng Increment có giá trị như thế nào? | Một vòng tạo giá trị, kiểm tra và thích ứng |
| **Sprint Planning** | Vì sao Sprint này có giá trị, làm gì và làm như thế nào? | Sprint Goal và Sprint Backlog làm cơ sở hành động |
| **Daily Scrum** | Hôm nay Developers cần thích ứng kế hoạch ra sao để đạt Sprint Goal? | Kiểm tra tiến triển và điều chỉnh Sprint Backlog |
| **Sprint Review** | Increment và môi trường sản phẩm cho thấy điều gì; Product Backlog nên đổi ra sao? | Hiểu chung về kết quả, phản hồi và bước tiếp theo |
| **Sprint Retrospective** | Chất lượng và hiệu quả làm việc có thể cải thiện ở đâu? | Một hay vài thay đổi có thể thực hiện và kiểm chứng |

Câu hỏi của sự kiện phải rõ trước khi nói về phòng họp, mẫu biên bản hay công cụ họp trực tuyến.

## 3. Hiểu đúng timebox: giới hạn để tập trung

**Timebox** là khung thời gian dành cho một hoạt động để ngăn nó kéo dài vô hạn và thúc đẩy sự tập trung vào kết quả. Trong các sự kiện Scrum, cần phân biệt:

- **Sprint:** có **độ dài cố định**, tối đa một tháng; là nhịp lặp bao trùm các sự kiện khác.
- **Sprint Planning, Sprint Review, Sprint Retrospective:** có **thời lượng tối đa theo Scrum cho Sprint một tháng**; với Sprint ngắn hơn, các sự kiện thường ngắn hơn.
- **Daily Scrum:** timebox **15 phút**, diễn ra mỗi ngày làm việc trong Sprint.

Một sự kiện có giới hạn tối đa bốn giờ **không có nghĩa phải họp đủ bốn giờ**. Nếu nhóm đã đạt mục đích của Review sau 90 phút, không cần tiếp tục chỉ để dùng hết thời gian. Ngược lại, khi gần hết timebox nhưng vấn đề vẫn lớn, nhóm cần xác định **quyết định tối thiểu cần có ngay, việc nào cần làm rõ tiếp và ai thực hiện**; không nên vội chốt sai chỉ để kết thúc đúng giờ.

### 3.1. Timebox không phải giới hạn đối với chất lượng phần mềm

Không nên hiểu “Sprint sắp hết” là lý do bỏ kiểm thử, giảm tiêu chuẩn bảo mật hoặc đánh dấu Done cho chức năng chưa đạt Definition of Done. Timebox giới hạn **khoảng làm việc và các sự kiện**, không làm thay đổi điều kiện sản phẩm được xem là hoàn tất.

Nếu một Product Backlog item chưa đạt DoD vào cuối Sprint, nó không phải là một phần của Increment hoàn tất. Nhóm minh bạch về trạng thái, kiểm tra nguyên nhân và điều chỉnh kế hoạch, thay vì gọi đó là “Done 80%”.

### 3.2. Timebox khác với lời hứa hoàn thành mọi hạng mục

Sprint được cố định về độ dài, nhưng phạm vi chi tiết có thể được làm rõ và thương lượng giữa Product Owner và Developers khi nhóm học thêm, miễn không làm mất Sprint Goal và không giảm chất lượng. Việc kết thúc Sprint đúng hạn không đồng nghĩa phải ép mọi PBI đã dự kiến đều hoàn thành bằng mọi giá.

### 3.3. Timebox giúp kiểm soát chi phí điều phối, không phải cấm trao đổi

Sau Daily Scrum, hai Developers vẫn có thể cùng debug lỗi trong một giờ nếu cần. Đó là hoạt động cộng tác để xử lý vấn đề, **không phải kéo dài Daily Scrum của cả nhóm**. Tương tự, các trao đổi làm rõ nghiệp vụ hoặc refinement có thể diễn ra ngoài các sự kiện chính thức khi phù hợp.

Scrum tạo các cơ hội chính thức để kiểm tra và thích ứng; nhóm không bị cấm nói chuyện, pairing hoặc phối hợp ở thời điểm khác.

## 4. Các giới hạn thời gian theo Scrum

Bảng dưới đây phản ánh các giới hạn trong **Scrum Guide 2020**. Những con số cho Sprint một tháng là **mức tối đa**, không phải lịch họp áp dụng y nguyên cho Sprint ngắn hơn.

| Sự kiện | Quy định thời gian | Thời điểm / nhịp | Điểm quan trọng |
| --- | --- | --- | --- |
| **Sprint** | Độ dài cố định **một tháng hoặc ngắn hơn** | Sprint mới bắt đầu ngay sau Sprint trước kết thúc | Là sự kiện bao trùm, chứa tất cả sự kiện Scrum còn lại |
| **Sprint Planning** | **Tối đa 8 giờ** với Sprint một tháng | Bắt đầu Sprint | Với Sprint ngắn, thường ngắn hơn |
| **Daily Scrum** | **15 phút** | **Mỗi ngày làm việc** của Sprint | Giữ cùng thời gian và địa điểm để giảm phức tạp |
| **Sprint Review** | **Tối đa 4 giờ** với Sprint một tháng | Gần cuối Sprint, trước Retrospective | Buổi làm việc để kiểm tra kết quả và điều chỉnh hướng đi |
| **Sprint Retrospective** | **Tối đa 3 giờ** với Sprint một tháng | **Kết thúc Sprint**, sau Review | Tập trung cải thiện chất lượng và hiệu quả |

**Không có công thức thời lượng chính thức kiểu “Sprint hai tuần thì tất cả thời lượng phải giảm đúng một nửa”.** Nhóm nên chọn thời lượng đủ đạt mục đích, thường ngắn hơn cho Sprint ngắn hơn, đồng thời không vượt những giới hạn Scrum tương ứng.

### 4.1. Scrum gồm năm sự kiện

Năm sự kiện là **Sprint** và bốn sự kiện diễn ra **trong Sprint**: Sprint Planning, Daily Scrum, Sprint Review, Sprint Retrospective. **Product Backlog refinement** là hoạt động liên tục để làm rõ các PBIs; nó **không phải sự kiện Scrum chính thức thứ sáu**, và Scrum Guide không quy định một timebox bắt buộc riêng cho nó.

### 4.2. Không trộn nhầm timebox một tháng với lịch hai tuần

Với Sprint hai tuần, việc đặt Planning tám giờ, Review bốn giờ và Retrospective ba giờ có thể là dấu hiệu lãng phí thời gian nếu nhóm không có nhu cầu tương ứng. Chúng là mức tối đa được nêu cho Sprint một tháng, **không phải bộ thời lượng bắt buộc của Sprint bất kỳ**.

Ví dụ lịch nhóm tự chọn cho Sprint hai tuần:

- Sprint Planning **2,5 giờ**.
- Daily Scrum **15 phút mỗi ngày làm việc**.
- Sprint Review **1,5 giờ**.
- Sprint Retrospective **1 giờ**.

Đây là **lựa chọn thực hành minh họa**, không phải tiêu chuẩn Scrum. Nếu backlog phức tạp hoặc stakeholder nhiều, nhóm có thể cần thời lượng khác nhưng vẫn phải bảo đảm mục đích và timebox phù hợp.

## 5. Sprint: nhịp cố định tạo khả năng kiểm tra thường xuyên

Sprint là “nhịp tim” của Scrum: nhóm chuyển ý tưởng thành giá trị trong những vòng ngắn. Theo Scrum, Sprint có độ dài cố định **tối đa một tháng**, Sprint mới bắt đầu **ngay khi Sprint trước kết thúc**.

### 5.1. Vì sao cố định độ dài Sprint?

Độ dài ổn định giúp nhóm:

1. Dự đoán được mốc kiểm tra, giảm lịch họp ngẫu hứng.
2. So sánh công việc trong các điều kiện tương đối gần nhau mà không lẫn việc Sprint kéo dài vô hạn.
3. Giới hạn khoảng thời gian phải chờ để nhận phản hồi chính thức.
4. Tạo cơ hội điều chỉnh mục tiêu ngắn hạn theo Product Goal một cách đều đặn.
5. Hạn chế rủi ro tăng lên vì chưa kiểm tra sản phẩm và cách làm việc.

Sprint ngắn thường tạo chu kỳ học hỏi nhanh hơn, nhưng cũng cần đủ thời gian cho công việc có ý nghĩa và việc tổ chức các sự kiện. Sprint dài tối đa một tháng là giới hạn của Scrum, **không có nghĩa mọi sản phẩm nên chọn một tháng**.

### 5.2. Những điều không được đánh đổi trong Sprint

Theo Scrum:

- **Không thực hiện thay đổi làm nguy hại đến Sprint Goal.**
- **Chất lượng không được suy giảm.**
- Product Backlog được làm rõ khi cần.
- Phạm vi có thể được làm rõ hoặc thương lượng với Product Owner khi học thêm.

Nếu một câu chuyện lớn hơn dự kiến, Developers trao đổi với Product Owner về phần việc có thể giao có ích mà vẫn hướng tới Sprint Goal. Không nên gia hạn Sprint tùy ý đến khi mọi thẻ Done; việc đó làm mất độ dài cố định và nhịp kiểm tra.

### 5.3. Có thể phát hành trong Sprint hay phải chờ Review?

Increment có thể được tạo ra nhiều lần trong Sprint và **có thể bàn giao trước khi Sprint kết thúc**. Sprint Review không phải cổng phê duyệt bắt buộc trước khi phát hành giá trị. Điều quan trọng là Increment đạt Definition of Done và thỏa các điều kiện triển khai hoặc vận hành cần thiết.

Ví dụ, nhóm có thể phát hành bản sửa lỗi thông báo vào giữa Sprint, quan sát phản hồi, rồi thảo luận dữ liệu ở Sprint Review. Đợi đến Review mới cho người dùng thấy sản phẩm không phải điều Scrum bắt buộc.

### 5.4. Trường hợp hủy Sprint

Nếu **Sprint Goal trở nên lỗi thời**, **Product Owner có thẩm quyền hủy Sprint**. Việc hủy Sprint hiếm khi hữu ích nếu chỉ có một yêu cầu mới hoặc một PBI bị chặn. Nhóm nên xem xét thay đổi mục tiêu sản phẩm/bối cảnh thật sự trước khi áp dụng quyết định này.

Không nhầm **hủy Sprint** với **nghỉ một ngày, dời Review vài hôm hoặc bỏ Retrospective**. Một Sprint đã được tổ chức cần có nhịp nhất quán; sự kiện được thiết kế để hỗ trợ kiểm tra và thích ứng, không phải những phần trang trí có thể bỏ tùy tiện.

## 6. Sprint Planning: dùng timebox để thống nhất Why – What – How

**Sprint Planning bắt đầu Sprint** và đặt nền tảng cho công việc sẽ được thực hiện. Timebox tối đa **8 giờ với Sprint một tháng**; với Sprint ngắn hơn thường ngắn hơn.

Scrum Team thảo luận ba chủ đề:

1. **Why – Vì sao Sprint này có giá trị?** Product Owner đề xuất cách sản phẩm có thể tăng giá trị. Toàn Scrum Team cộng tác xác định **Sprint Goal** trước khi kết thúc Planning.
2. **What – Có thể làm gì trong Sprint?** Developers trao đổi với Product Owner và chọn các Product Backlog items có thể hoàn tất phù hợp với mục tiêu và năng lực.
3. **How – Công việc được thực hiện như thế nào?** Developers lập kế hoạch để tạo Increment đáp ứng Definition of Done; kế hoạch có thể bao gồm chia nhỏ PBIs thành công việc cụ thể.

### 6.1. Chuẩn bị đúng để dùng thời gian Planning hiệu quả

**Product Owner** làm rõ Product Goal, đề xuất các hạng mục đáng ưu tiên và cung cấp bối cảnh giá trị.

**Developers** xem dữ liệu năng lực đã biết, phụ thuộc, kỹ năng cần thiết, rủi ro kỹ thuật và cách đạt DoD.

**Scrum Master** giúp Scrum Team hiểu mục đích và timebox của sự kiện, hỗ trợ cuộc thảo luận đi đến kết quả.

Nếu Product Backlog còn thiếu thông tin, đội có thể dành một phần Planning để làm rõ nhưng không nên mặc định biến Planning thành buổi viết lại toàn bộ backlog. **Refinement là hoạt động liên tục**, thường giúp các hạng mục gần được chọn đủ rõ trước khi Sprint bắt đầu.

### 6.2. Dấu hiệu Planning đang mất tập trung

- Mỗi người đọc từng ticket chưa ai hiểu, còn câu hỏi nghiệp vụ cơ bản chưa có lời giải.
- Cuộc họp chỉ hỏi “cần đạt bao nhiêu points?” nhưng không có Sprint Goal.
- Product Owner giao việc kỹ thuật chi tiết cho từng người trong khi Developers không tham gia lập kế hoạch.
- Nhóm cam kết mọi hạng mục dù có phụ thuộc và nghỉ phép chưa được xem xét.
- Hết giờ mà không biết Sprint Goal hoặc những công việc được chọn.

Khi gần hết timebox, cần **ưu tiên Sprint Goal và phạm vi thực tế**, ghi lại các câu hỏi chưa giải quyết và không ép nhận những hạng mục chưa đủ rõ chỉ để có danh sách dài.

### 6.3. Ví dụ đầu ra Planning

~~~text
Product Goal: Học viên tự đăng ký workshop và hiểu kết quả.
Sprint Goal: Học viên thử nghiệm gửi yêu cầu đăng ký
             và nhận trạng thái dễ hiểu mà không hỏi riêng điều phối viên.

PBIs dự kiến:
- Gửi yêu cầu và ghi nhận một kết quả rõ ràng.
- Kiểm tra trường hợp workshop đã hết chỗ.
- Cập nhật cách diễn đạt "chờ xác nhận".

Ràng buộc:
- Không xác nhận vượt số chỗ.
- Chỉ hiển thị dữ liệu của người dùng đúng quyền.
- Mọi Increment phải đạt Definition of Done.

Câu hỏi cần làm rõ:
- Điều phối viên xác nhận trong bao lâu?
- Thông báo nào đủ rõ với học viên lần đầu?

Cách phối hợp:
- Pairing ở phần kiểm tra đồng thời.
- Dùng thử sớm với nhóm học viên nhỏ.
- Xem tiến triển về Sprint Goal mỗi ngày.
~~~

Đây là **ví dụ về kết quả cần trao đổi**, không phải mẫu Sprint Backlog bắt buộc.

## 7. Daily Scrum: 15 phút để kiểm tra và điều chỉnh kế hoạch

**Daily Scrum** là sự kiện **15 phút dành cho Developers của Scrum Team**, diễn ra **mỗi ngày làm việc của Sprint**. Để giảm phức tạp, nó được tổ chức **cùng thời điểm và địa điểm**. Với nhóm phân tán, “địa điểm” có thể là một không gian họp trực tuyến ổn định nếu phù hợp.

Mục đích là **kiểm tra tiến triển hướng tới Sprint Goal và thích ứng Sprint Backlog khi cần**, điều chỉnh công việc dự kiến tiếp theo.

### 7.1. Daily Scrum không phải buổi báo cáo cho Product Owner

Nếu mọi người chỉ đọc “hôm qua làm gì, hôm nay làm gì” rồi chờ người quản lý xác nhận, nhóm có thể bỏ lỡ việc đang bị chặn hoặc nguy cơ không đạt Sprint Goal. Scrum không bắt buộc định dạng ba câu hỏi; Developers được chọn cấu trúc phù hợp miễn cuộc họp tập trung vào mục tiêu và tạo kế hoạch khả thi cho ngày tiếp theo.

Các câu hỏi hữu ích:

- “Phần nào của Sprint Goal vẫn chưa có Increment có thể kiểm tra?”
- “PBI nào đang bị chặn hoặc có tuổi công việc lớn bất thường?”
- “Hôm nay cần ai cùng hoàn tất việc đang làm trước khi kéo việc mới?”
- “Có thay đổi nào cần trao đổi với Product Owner để không làm lệch mục tiêu?”
- “Kiểm thử hoặc tích hợp nào đang đe dọa DoD?”

### 7.2. Ví dụ Daily Scrum hiệu quả

Một nhóm đang làm luồng gửi đăng ký:

> **Nam:** “Phần hiển thị trạng thái đã tích hợp nhưng tình huống hai người chọn suất cuối đang thất bại. Nếu không xử lý, chúng ta không đạt Sprint Goal an toàn.”
>
> **Linh:** “Tôi sẽ cùng Nam xử lý kiểm thử đồng thời ngay sau Daily. Tôi dừng bắt đầu story báo cáo mới.”
>
> **Mai:** “Tôi sẽ kiểm tra thông báo của tình huống hết chỗ với Product Owner để nhóm không hiển thị xác nhận sai.”

Kết quả của 15 phút là **kế hoạch phối hợp mới**, không phải bản tổng kết cá nhân. Sau Daily, Nam và Linh có thể làm việc chuyên sâu cùng nhau; không cần giữ tất cả mọi người trong cuộc họp để xem từng dòng lỗi.

### 7.3. Ai tham gia?

Daily Scrum dành cho **Developers**. Nếu Product Owner hoặc Scrum Master đang trực tiếp thực hiện công việc thuộc Sprint Backlog, họ tham gia như Developers đối với công việc đó. Scrum Master giúp nhóm hiểu và thực hành Scrum nhưng không nhất thiết phải điều hành hay nghe báo cáo từng ngày.

Các bên khác có thể cần trao đổi công việc, nhưng không nên biến Daily Scrum thành cuộc họp kiểm tra của nhiều cấp quản lý.

### 7.4. Nếu vấn đề không giải quyết xong trong 15 phút?

Khi một vấn đề kỹ thuật cần phân tích lâu:
1. Nêu ngắn gọn **ảnh hưởng đến Sprint Goal**.
2. Chốt **ai cùng giải quyết, khi nào và bằng cách nào**.
3. Ghi lại quyết định điều chỉnh Sprint Backlog.
4. Kết thúc Daily đúng timebox; nhóm liên quan tiếp tục trao đổi sau đó.

Daily Scrum kết thúc đúng giờ không có nghĩa vấn đề đã được sửa. **Kết quả cần có là công việc tiếp theo rõ ràng và rào cản được đưa ra ánh sáng.**

## 8. Sprint Review: timebox cho phản hồi sản phẩm có giá trị

**Sprint Review** có timebox **tối đa 4 giờ cho Sprint một tháng**; Sprint ngắn hơn thường có Review ngắn hơn. Đây là **sự kiện gần cuối Sprint**, trước Sprint Retrospective.

Scrum Team và các stakeholder liên quan cùng **kiểm tra kết quả Sprint và tiến triển hướng tới Product Goal**, thảo luận điều đã thay đổi trong môi trường và cân nhắc cần làm gì tiếp theo. Product Backlog có thể được điều chỉnh theo phản hồi.

### 8.1. Review là buổi làm việc, không chỉ trình diễn

Một Sprint Review có ích thường bao gồm:

1. Nhắc lại **Product Goal** và mục tiêu của Sprint.
2. Quan sát **Increment đạt DoD**, sử dụng tình huống người dùng thật hoặc mô phỏng phù hợp.
3. Chia sẻ phản hồi người dùng, dữ liệu kết quả và những điều chưa chắc.
4. Thảo luận ảnh hưởng của thay đổi thị trường, nghiệp vụ hoặc rủi ro đến thứ tự ưu tiên.
5. Xem các lựa chọn tiếp theo, thông tin cần xác minh và cập nhật Product Backlog khi phù hợp.

Nếu Sprint không hoàn tất tất cả PBIs dự kiến, nhóm cần trình bày trung thực: điều gì đã đạt DoD, điều gì chưa và vì sao. **Không trình bày hạng mục chưa đạt DoD như Increment hoàn tất** chỉ để có “demo đẹp”.

### 8.2. Review không phải cổng phát hành

Như đã nêu, Increment có thể được phát hành trước Review. Review là thời điểm **kiểm tra, học hỏi và điều chỉnh** cùng stakeholder; không phải điều kiện tiên quyết để phần mềm được đưa vào sử dụng. Đồng thời, một buổi Review thành công không tự chứng minh khách hàng thực sự đã nhận giá trị nếu chưa có dữ liệu sử dụng thích hợp.

### 8.3. Ví dụ quyết định từ Review

Dữ liệu **giả định** từ một đợt dùng thử:
- 12/15 học viên gửi được yêu cầu đăng ký.
- Chỉ 7/15 hiểu đúng sự khác biệt giữa “đã nhận yêu cầu” và “đã có chỗ”.
- 5/15 vẫn phải nhắn hỏi ban tổ chức.
- Kiểm thử xử lý đồng thời cho suất cuối còn một trường hợp chưa đạt.

Thay vì chỉ khen “đã hoàn thành 18 points”, nhóm có thể kết luận:

> “Khả năng gửi yêu cầu đã hoạt động trong phần lớn lượt thử, nhưng lợi ích không phải hỏi lại trạng thái chưa được chứng minh. Cần làm rõ thông báo và bảo vệ quy tắc xác nhận trước khi mở rộng.”

Số liệu mẫu nhỏ không chứng minh nguyên nhân duy nhất; nó cung cấp **tín hiệu để kiểm tra tiếp và cập nhật thứ tự backlog**.

## 9. Sprint Retrospective: timebox để cải thiện cách làm việc

**Sprint Retrospective** có timebox **tối đa 3 giờ với Sprint một tháng**, thường ngắn hơn cho Sprint ngắn. Nó **kết thúc Sprint** và diễn ra **sau Sprint Review**.

Mục đích là lập kế hoạch cải thiện **chất lượng và hiệu quả**. Scrum Team xem cách Sprint vừa qua diễn ra về con người, tương tác, quy trình, công cụ và Definition of Done; nhận diện điều làm nhóm lệch hướng hoặc tạo vấn đề, rồi chọn cải tiến có ích.

### 9.1. Retrospective không phải phiên quy lỗi cá nhân

Một Retro có thể thảo luận:
- Vì sao review mã kéo dài và story chưa đạt DoD?
- Lúc nào backlog thiếu ví dụ nghiệp vụ khiến nhóm chờ làm rõ?
- Daily Scrum có giúp thay đổi kế hoạch hay chỉ đọc status?
- Việc khẩn cấp được đưa vào Sprint theo chính sách nào?
- Cách giữ Sprint Goal có tạo ra chất lượng thấp hoặc làm thêm giờ thường xuyên không?

Không nên hỏi “Ai làm Sprint bị thất bại?”. Câu hỏi tốt hơn là **“Dữ liệu và tình huống nào cho thấy hệ thống làm việc chưa hiệu quả, và thử thay đổi nhỏ nào sẽ giúp?”**

### 9.2. Một Retro ngắn nhưng có kết quả

Ví dụ nhóm dành **60 phút** cho Sprint hai tuần:

| Phần | Thời lượng minh họa | Đầu ra |
| --- | ---: | --- |
| Tập trung vào mục đích và dữ liệu Sprint | 10 phút | Những quan sát chung có bằng chứng |
| Nhận diện điều hữu ích và điều cản trở | 15 phút | Một số nguyên nhân giả định để kiểm tra |
| Chọn vấn đề có tác động cao | 10 phút | Một ưu tiên cải tiến |
| Thiết kế thay đổi và cách kiểm chứng | 20 phút | Hành động, người phối hợp, tín hiệu kết quả |
| Chốt và xác định mốc xem lại | 5 phút | Điều nhóm sẽ kiểm tra trong Sprint tới |

Tổng là **60 phút**. Đó chỉ là ví dụ điều phối, không phải cấu trúc bắt buộc theo Scrum.

Hành động có thể là:
> “Sprint tới, trước khi bắt đầu PBI có rủi ro về trạng thái thanh toán, Developers và Product Owner sẽ làm rõ một tình huống thành công và một trường hợp lỗi. Cuối Sprint, nhóm kiểm tra xem có giảm số lần story phải dừng để hỏi lại nghiệp vụ không.”

### 9.3. Kiểm chứng cải tiến thay vì lưu biên bản rồi quên

Một quyết định Retro nên trả lời:
- **Thay đổi cụ thể là gì?**
- **Ai cùng thực hiện?**
- **Khi nào áp dụng?**
- **Tín hiệu nào cho biết có ích hay không?**
- **Khi nào nhóm xem lại?**

Một hoặc hai cải tiến làm được thường có giá trị hơn danh sách mười đề xuất không có người theo dõi. Những cải tiến tác động lớn có thể được đưa vào Sprint Backlog tiếp theo nếu nhóm thấy phù hợp.

## 10. Thiết kế nhịp Sprint hai tuần: ví dụ lịch thực hành

Một nhóm làm việc từ thứ Hai đến thứ Sáu, chọn **Sprint hai tuần làm việc**. Ví dụ lịch dưới đây giả định không có ngày nghỉ lễ, nhóm có múi giờ đủ giao nhau và các bên tham gia đã thống nhất lịch.

| Thời điểm | Hoạt động | Thời lượng ví dụ | Mục đích |
| --- | --- | --- | --- |
| **Thứ Hai tuần 1, đầu ngày** | Sprint Planning | 2 giờ 30 phút | Xác định Sprint Goal, PBIs phù hợp và kế hoạch bước đầu |
| **Mỗi ngày làm việc trong Sprint** | Daily Scrum vào một giờ cố định | 15 phút | Kiểm tra Sprint Goal, thích ứng Sprint Backlog |
| **Trong hai tuần, khi cần** | Refinement, pairing, kiểm thử, trao đổi nghiệp vụ | Tùy nhu cầu | Giữ các PBIs rõ và tạo Increment đạt DoD |
| **Thứ Sáu tuần 2, gần cuối ngày** | Sprint Review | 1 giờ 30 phút | Kiểm tra Increment, Product Goal và phản hồi stakeholder |
| **Thứ Sáu tuần 2, sau Review** | Sprint Retrospective | 1 giờ | Kiểm tra cách làm việc và thống nhất cải tiến |
| **Sau khi Sprint này kết thúc** | Sprint kế tiếp bắt đầu ngay | Độ dài cố định như đã thống nhất | Giữ nhịp Scrum liên tục |

Lưu ý: Daily Scrum vẫn là sự kiện của **mỗi ngày làm việc trong Sprint**, kể cả khi ngày đó có Planning hoặc Review nếu đó là ngày làm việc và phù hợp thời điểm nhóm tổ chức. Trong thực tế, nhóm có thể chọn giờ Planning/Review để tránh trùng Daily; lịch trên chỉ cho thấy **nhịp**, không áp đặt từng khung giờ.

### 10.1. Sơ đồ nhịp sự kiện

~~~text
SPRINT HAI TUẦN (ví dụ)
Đầu Sprint                                                Cuối Sprint
|                                                                  |
Planning — Daily — Daily — Daily — ... — Daily — Review — Retro
|                                                                  |
   Phát triển + kiểm thử + refinement khi cần + tạo Increment
   <---------- Kiểm tra Sprint Goal và điều chỉnh hằng ngày ------>
|                                                                  |
Sprint Goal được xác định                  Phản hồi và cải tiến tiếp theo
                                        Sprint mới bắt đầu ngay sau đó
~~~

Các sự kiện không thay thế việc phát triển, kiểm thử, thiết kế, hỗ trợ vận hành và cộng tác liên tục. Nhóm có thể có nhiều Increment trong một Sprint; chỉ những phần đạt DoD mới được coi là hoàn tất.

### 10.2. Tổng thời gian tổ chức sự kiện có ý nghĩa thế nào?

Với ví dụ trên, nếu có **10 ngày làm việc** và Daily Scrum diễn ra 10 lần:

~~~text
Planning:       150 phút
Daily Scrum: 10 x 15 = 150 phút
Review:          90 phút
Retrospective:   60 phút
Tổng thời lượng sự kiện theo lịch: 450 phút = 7 giờ 30 phút
~~~

Đây là tổng thời lượng của **các phiên sự kiện trên lịch**, không phải một số duy nhất về giờ tham dự của mọi vai trò. Daily Scrum dành cho Developers; thành phần tham dự các sự kiện khác cũng khác nhau. Tổng trên cũng **không gồm** refinement, pairing, trao đổi với khách, hỗ trợ sự cố và các hoạt động cần thiết khác.

Không nên nhìn “7 giờ 30 phút” rồi kết luận nhịp Scrum lãng phí. Câu hỏi có ích hơn là: **Những sự kiện này có giúp tránh chờ đợi, phát hiện lỗi sớm, ra quyết định tốt hơn và giao Increment có giá trị không?**

### 10.3. Giữ cùng giờ và địa điểm cho Daily Scrum

Chọn giờ phù hợp để Developers tham dự vào mỗi ngày làm việc, chẳng hạn **9:15–9:30** tại cùng không gian họp trực tuyến hoặc khu vực nhóm. Tránh đổi mỗi ngày theo lịch trống của cấp quản lý. Nếu có thành viên ở nhiều múi giờ, cần chọn khoảng giao nhau hợp lý, không khiến một số người thường xuyên phải dự vào ban đêm.

Nếu thay đổi giờ họp do một sự kiện đặc biệt, nhóm nên thông báo rõ, tránh biến ngoại lệ thành sự thay đổi không thể dự đoán.

## 11. Nhịp đều cần đi cùng khả năng thích ứng

**Tính nhất quán** không phải sự cứng nhắc. Scrum cho phép nhóm học từ bằng chứng và điều chỉnh kế hoạch. Điểm quan trọng là không làm mất cơ chế kiểm tra đều đặn.

### 11.1. Những điều nên ổn định

- Độ dài Sprint đã thống nhất trong giai đoạn làm việc phù hợp.
- Thời điểm và địa điểm Daily Scrum để giảm chi phí điều phối.
- Mục đích, thành phần có trách nhiệm và timebox của từng sự kiện.
- Definition of Done và cách xác minh Increment.
- Các cam kết trong Scrum: Product Goal, Sprint Goal và DoD được hiểu đúng.

### 11.2. Những điều có thể thay đổi dựa trên bằng chứng

- Thứ tự Product Backlog.
- Phạm vi chi tiết của Sprint qua trao đổi phù hợp giữa Product Owner và Developers.
- Cách Developers tổ chức, phối hợp, chia nhỏ và kiểm thử công việc.
- Ví dụ được dùng trong Sprint Review, tùy Increment và phản hồi hiện tại.
- Nội dung cần thảo luận trong Daily Scrum hoặc Retrospective.
- Lựa chọn thay đổi cách làm việc sau Retrospective.

Không nên dùng “linh hoạt” để giải thích việc bỏ sự kiện có chủ đích chỉ vì kết quả chưa đẹp. Cũng không nên dùng “đúng quy trình” để biện minh cho lịch họp quá dài hoặc một cuộc họp không còn phục vụ mục đích.

## 12. Xử lý các tình huống ngoại lệ và gián đoạn

Một nhịp thực tế luôn có nghỉ phép, lỗi khẩn, sự cố mạng, thay đổi nghiệp vụ và lịch của stakeholder. Cần xử lý theo **mục đích sự kiện, trách nhiệm và mức độ tác động**, không chỉ theo thói quen đặt lịch.

| Tình huống | Rủi ro nếu xử lý kém | Cách phản ứng phù hợp |
| --- | --- | --- |
| Planning sắp hết timebox nhưng backlog còn mơ hồ | Nhận việc không rõ, Sprint Goal yếu | Ưu tiên Sprint Goal và phạm vi khả thi, ghi câu hỏi; tiếp tục refinement đúng lúc |
| Daily Scrum kéo dài 45 phút vì debug | Cả nhóm mất thời gian, Daily thành họp kỹ thuật | Nêu cản trở, chọn người làm tiếp sau Daily, cập nhật kế hoạch |
| Stakeholder quan trọng vắng Review | Mất một góc nhìn phản hồi | Mời đúng người, chia sẻ bằng chứng phù hợp, thu phản hồi bổ sung; không mặc định hủy Review |
| Sprint không có nhiều hạng mục Done | Review biến thành “không có gì” hoặc che trạng thái | Kiểm tra Increment thực sự có, minh bạch điều chưa xong, rủi ro và tiến triển mục tiêu |
| Có lỗi production nghiêm trọng | Người dùng bị ảnh hưởng nếu nhóm chờ đến cuối Sprint | Kích hoạt ứng phó sự cố, minh bạch tác động, điều chỉnh công việc với PO và Developers |
| Một thành viên nghỉ phép | Nhóm chờ người để quyết định hoặc thay lịch vô hạn | Chuẩn bị dự phòng, chia sẻ kiến thức, điều chỉnh năng lực; giữ nhịp khả thi |
| Nhóm làm ở nhiều múi giờ | Người dự bị ép tham gia ngoài giờ hợp lý | Chọn giờ chung công bằng, dùng tài liệu và trao đổi bất đồng bộ hỗ trợ |
| Ngày nghỉ lễ rơi vào lịch Review | Phải chọn giữa bỏ phản hồi và họp lúc nghỉ | Thiết kế lịch Sprint nhất quán có xét lịch nghỉ, thông báo điều chỉnh từ sớm |
| Sprint Goal bị lỗi thời do thay đổi căn bản | Tiếp tục làm việc không còn giá trị | Product Owner xem xét thẩm quyền hủy Sprint nếu Sprint Goal obsolete |
| Retro lặp lại vấn đề cũ nhưng không có cải tiến | Sự kiện thành nơi than phiền | Chọn một thử nghiệm nhỏ, người phối hợp và mốc kiểm chứng |

### 12.1. Khi có sự cố production

Đừng để lịch Daily Scrum hay Sprint Review ngăn phản ứng kịp thời với sự cố gây hại. Nhóm cần bảo vệ người dùng, thực hiện quy trình ứng phó theo mức độ nghiêm trọng, ghi nhận công việc phát sinh và cùng Product Owner xem ảnh hưởng lên Sprint Goal.

Sau khi hệ thống ổn định, nhóm có thể mang bằng chứng sự cố vào Review (tác động lên sản phẩm) và Retrospective (cách phối hợp, kiểm thử, vận hành). Hai sự kiện có mục đích khác nhau; tránh biến Review thành phiên truy lỗi cá nhân hoặc Retro thành buổi chỉ tính doanh thu.

### 12.2. Nếu Sprint Goal không còn đạt được

Có sự khác biệt giữa **Sprint Goal bị thách thức** và **Sprint Goal trở nên lỗi thời**:

- Nếu mục tiêu vẫn có giá trị nhưng một story bị chặn, Scrum Team xem cách điều chỉnh phạm vi và kế hoạch.
- Nếu bối cảnh sản phẩm thay đổi khiến mục tiêu không còn ý nghĩa, Product Owner có thể xem xét hủy Sprint.

Không nên hủy Sprint chỉ để “bắt đầu lại cho đẹp velocity”, cũng không nên kéo dài Sprint đến khi kế hoạch hoàn tất. Những cách làm đó che mất thông tin về thực tế.

### 12.3. Khi nhóm phân tán, làm việc bất đồng bộ

Công cụ chat và bảng công việc có thể hỗ trợ chuẩn bị thông tin trước sự kiện, ghi quyết định sau sự kiện và giảm thời gian kể lại bối cảnh. Tuy nhiên, nếu nhóm bỏ hoàn toàn Daily Scrum trực tiếp và chỉ gửi báo cáo bất đồng bộ, cần nhìn nhận rằng thực hành đó **không còn tuân thủ nguyên dạng sự kiện 15 phút mỗi ngày làm việc theo Scrum Guide**. Không nên trình bày như thể Scrum yêu cầu thay Daily bằng cập nhật chat.

Nhóm có thể tìm một khung họp ngắn ổn định và sử dụng phương thức bất đồng bộ cho các trao đổi chi tiết. Nếu tổ chức cần một mô hình khác vì múi giờ, có thể cân nhắc phối hợp Agile phù hợp thay vì gọi mọi thói quen bất đồng bộ là Scrum chuẩn.

## 13. Minh bạch trong sự kiện: nói về bằng chứng, không chỉ cảm giác

### 13.1. Mỗi sự kiện cần dữ liệu đúng mục đích

| Sự kiện | Thông tin nên xem | Điều nên tránh |
| --- | --- | --- |
| Planning | Product Goal, các PBIs được làm rõ, năng lực, phụ thuộc, DoD | Chọn hạng mục chỉ để đạt tổng story points đẹp |
| Daily Scrum | Sprint Goal, Sprint Backlog hiện tại, hạng mục bị chặn, khả năng hoàn tất | Báo cáo cá nhân dài hoặc đọc lại toàn bộ bảng |
| Review | Increment đạt DoD, phản hồi người dùng, thay đổi bối cảnh, Product Backlog | Demo thành tích không có trao đổi hoặc hứa giao mọi hạng mục |
| Retrospective | Điều đã xảy ra, chất lượng, thời gian chờ, cộng tác, các cải tiến trước | Quy lỗi cá nhân, liệt kê quá nhiều hành động không theo dõi |
| Nhịp Sprint | Sản phẩm tăng dần, chu kỳ phản hồi, chất lượng và giá trị | Đo thành công bằng số giờ họp hoặc số points một cách độc lập |

### 13.2. Đầu ra, outcome và tác động là những câu hỏi khác nhau

**Output:** nhóm đã tạo được phần mềm nào, chức năng nào đã đạt DoD?

**Outcome:** hành vi hoặc trải nghiệm của người dùng thay đổi ra sao khi chức năng đó được sử dụng?

**Impact:** sản phẩm tạo tác động rộng hơn thế nào cho tổ chức và người liên quan?

Ví dụ, hoàn tất giao diện hiển thị trạng thái là output; học viên ít phải hỏi “tôi đã có chỗ chưa?” là outcome; công điều phối được giảm bền vững có thể là impact. Một Sprint Review có ích có thể xem cả ba nếu có dữ liệu, nhưng không nên giả định output luôn kéo theo outcome tích cực.

### 13.3. Các tín hiệu để đánh giá nhịp sự kiện

Không có KPI chính thức bắt buộc cho “chất lượng họp Scrum”. Nhóm có thể chọn vài tín hiệu phù hợp:

- **Mức rõ của Sprint Goal:** thành viên có giải thích giống nhau giá trị Sprint không?
- **Tốc độ nhận diện cản trở:** có tình huống nào chờ nhiều ngày dù Daily Scrum diễn ra đều?
- **Tuổi hạng mục đang làm (work item age):** việc nào đang kéo dài bất thường?
- **Cycle time và throughput:** dòng công việc có trở nên dễ dự báo hơn không?
- **Tỷ lệ Increment đạt DoD khi được xem xét:** điều gì thường khiến công việc bị dồn về cuối?
- **Phản hồi Product Goal:** stakeholder có đưa ra quyết định thay đổi backlog nhờ Review không?
- **Cải tiến Retro được kiểm chứng:** nhóm đã thử và đánh giá thay đổi nào ở vòng sau?
- **Chất lượng và độ ổn định:** lỗi nghiêm trọng, sự cố và phải làm lại có tăng không?
- **Bền vững:** lịch sự kiện có tạo áp lực ngoài giờ hoặc khiến thành viên thiếu thời gian tập trung không?

Những tín hiệu này để **học và điều chỉnh hệ thống làm việc**, không phải chấm điểm cá nhân hoặc thưởng phạt Scrum Master dựa vào số biên bản đã tạo.

## 14. Tình huống xuyên suốt: nhịp hai tuần của nhóm đặt workshop

### 14.1. Bối cảnh

Một Scrum Team phát triển hệ thống đăng ký workshop. Product Goal là giúp học viên tự chọn buổi còn chỗ, gửi đăng ký và hiểu rõ trạng thái; điều phối viên kiểm soát số chỗ chính xác.

Nhóm chọn Sprint hai tuần. Product Owner làm rõ giá trị và các PBIs; Developers lập kế hoạch thực hiện; Scrum Master hỗ trợ hiệu quả Scrum. Một số học viên và điều phối viên đồng ý tham gia dùng thử trong phạm vi phù hợp.

### 14.2. Sprint Planning: chọn mục tiêu nhỏ có thể thử

Trong Planning, nhóm thống nhất Sprint Goal:

> “Học viên trong đợt thử có thể gửi yêu cầu đăng ký và biết yêu cầu đang chờ hay đã được xác nhận, không phải nhắn hỏi ngay sau khi gửi.”

Developers chọn các PBIs: luồng gửi yêu cầu, hiển thị trạng thái, tình huống buổi hết chỗ và kiểm thử an toàn dữ liệu. Product Owner xác nhận quy tắc nghiệp vụ còn mơ hồ về thời điểm xác nhận. Nhóm ghi rủi ro và trao đổi bổ sung với điều phối viên ngay trong Sprint.

Điểm quan trọng: **Planning kết thúc với mục tiêu và kế hoạch thực tế**, không cần tất cả câu hỏi tương lai đã được giải quyết.

### 14.3. Daily Scrum: phát hiện cản trở sớm

Ngày làm việc thứ tư, Developers phát hiện kiểm thử hai người cùng đăng ký suất cuối có nguy cơ vượt số chỗ. Trong Daily Scrum:

- Nêu rủi ro ảnh hưởng Sprint Goal và DoD.
- Hai Developers cùng xử lý tình huống đồng thời sau Daily.
- Người khác tạm ngừng mở thêm story để hỗ trợ kiểm tra.
- Product Owner được trao đổi để làm rõ quy tắc xác nhận đúng.

Nhóm không mở cuộc họp status kéo dài. **Daily Scrum đưa ra quyết định phối hợp**, còn phân tích sâu diễn ra sau đó.

### 14.4. Bàn giao và thu phản hồi trong Sprint

Khi một lát cắt đáp ứng DoD, nhóm đưa nó vào môi trường dùng thử phù hợp trước cuối Sprint. Người học viên thử cho rằng “đã tiếp nhận” nghĩa là đã chắc chắn giữ chỗ, dù thực tế điều phối viên vẫn phải duyệt.

Nhóm ghi phản hồi, hỏi cách diễn đạt nào người dùng hiểu và kiểm tra mức rủi ro, nhưng không tự tuyên bố đã đạt Product Goal chỉ vì chức năng chạy được.

### 14.5. Sprint Review: thay đổi góc nhìn về ưu tiên

Trong Review, nhóm cùng stakeholder xem một Increment đạt DoD và kết quả dùng thử giả định:

| Tín hiệu trong đợt thử | Kết quả minh họa |
| --- | ---: |
| Học viên gửi yêu cầu thành công | 13/15 |
| Học viên hiểu đúng “chờ xác nhận” | 8/15 |
| Người phải hỏi lại ban tổ chức | 5/15 |
| Tình huống đồng thời còn chưa kiểm chứng đủ | 1 |

Nhóm thảo luận: phần gửi yêu cầu có dấu hiệu hoạt động nhưng **trạng thái chưa đủ rõ** và một trường hợp rủi ro chưa được xác minh. Product Owner cân nhắc đưa việc cải thiện thông báo và kiểm thử đồng thời lên trước báo cáo quản trị nâng cao.

**Dữ liệu hoàn toàn giả định** để luyện phân tích; 13/15 không thể chứng minh toàn bộ người dùng sẽ hoàn tất với tỷ lệ tương tự.

### 14.6. Sprint Retrospective: chọn một cải tiến thực hiện được

Nhóm thấy tình huống đồng thời được phát hiện quá muộn vì ban đầu chỉ thử trường hợp một người gửi yêu cầu. Họ chọn cải tiến:

> “Sprint tới, với mọi PBI ảnh hưởng số chỗ, Developers và Product Owner sẽ cùng kiểm tra ít nhất một tình huống đồng thời hoặc trường hợp biên quan trọng trước khi bắt đầu triển khai. Đến Retro sau, nhóm kiểm tra có giảm số lần phải dừng story vì thiếu ví dụ nghiệp vụ hay không.”

Hành động có người phối hợp và mốc xem lại. Nó không biến Retro thành bảng thành tích; nó tạo **một thử nghiệm cải tiến**.

### 14.7. Sprint mới: giữ nhịp, thay đổi quyết định

Sprint mới bắt đầu ngay khi Sprint trước kết thúc. Product Backlog đã được điều chỉnh từ Review; Developers dùng thông tin mới khi chọn mục tiêu và lập kế hoạch. Nhịp được giữ ổn định trong khi **thứ tự và cách làm thay đổi theo bằng chứng**.

Đó là giá trị của timebox và cadence: nhóm không trì hoãn kiểm tra vô thời hạn nhưng cũng không coi kế hoạch ban đầu là bất biến.

## 15. Các sai lầm thường gặp

| Sai lầm | Vì sao gây hại | Cách điều chỉnh |
| --- | --- | --- |
| Daily Scrum kéo dài thành một giờ báo cáo | Mất tập trung, không còn thời gian cho phối hợp chuyên sâu | Giữ 15 phút, nói về Sprint Goal, tách điều tra chi tiết sau |
| Luôn dùng hết thời lượng tối đa của sự kiện | Thêm cuộc thảo luận khi mục đích đã đạt | Kết thúc khi đã đạt mục đích, không cần dùng hết timebox |
| Planning chỉ để cộng story points | Không tạo định hướng giá trị, nhận việc thiếu căn cứ | Bắt đầu bằng Why, làm rõ What và How, thống nhất Sprint Goal |
| Review chỉ demo màn hình cho cấp quản lý | Không thu phản hồi có ích để điều chỉnh backlog | Mời stakeholder trao đổi về Increment, Product Goal và bối cảnh |
| Hủy Review vì ít story Done | Che trạng thái và mất cơ hội kiểm tra | Minh bạch phần đạt DoD, vấn đề và quyết định tiếp theo |
| Retro chỉ “điểm danh lỗi của người làm” | Mất an toàn tâm lý, lặp vấn đề | Phân tích hệ thống và chọn cải tiến có thể kiểm chứng |
| Bỏ Retro vì Sprint không thành công | Mất cơ hội học đúng lúc cần | Giữ sự kiện, ưu tiên vấn đề có tác động lớn |
| Dời thời điểm Daily mỗi ngày | Tăng chi phí sắp lịch, khó tạo thói quen | Chọn cùng giờ và nơi phù hợp mỗi ngày làm việc |
| Kéo dài Sprint để hoàn tất mọi việc | Mất nhịp cố định, che khả năng giao thực tế | Kết thúc đúng độ dài, minh bạch trạng thái chưa đạt DoD |
| Dùng Sprint Review như cửa phê duyệt phát hành | Phản hồi bị chậm không cần thiết | Phát hành Increment đạt DoD khi đủ điều kiện; Review vẫn kiểm tra và thích ứng |
| Xem refinement là sự kiện Scrum bắt buộc có timebox chính thức | Gắn sai quy định, thêm nghi thức hình thức | Coi refinement là hoạt động liên tục; tổ chức khi giúp PBIs rõ hơn |
| Đánh đổi kiểm thử để kịp kết thúc Sprint | Sản phẩm thiếu tin cậy, giá trị không bền | Giữ DoD, điều chỉnh phạm vi và báo trung thực |
| Chọn thời gian họp bất lợi cho người ở xa | Cộng tác khó bền vững | Thiết kế giờ giao nhau công bằng và tài liệu bổ trợ |
| Giữ lịch họp nhưng không có dữ liệu hoặc quyết định | Scrum thành nghi lễ, không có học hỏi | Xác định mục đích, đầu vào và hành động sau từng sự kiện |
| Chỉ đo số giờ họp ít đi | Có thể giảm họp nhưng tăng chờ và làm lại | Cân bằng thời gian điều phối với flow, quality và outcome |

## 16. Bài thực hành: thiết kế nhịp Scrum và xử lý gián đoạn

### 16.1. Bối cảnh

Một Scrum Team sáu người chọn Sprint **hai tuần**, làm việc năm ngày mỗi tuần. Nhóm phát triển nền tảng đặt lịch. Product Goal là giúp người dùng tự gửi yêu cầu và kiểm tra trạng thái mà không phải liên hệ thủ công.

Hiện tại:
- Sprint Planning thường kéo dài sáu giờ.
- Daily Scrum trung bình 35 phút vì mọi người đọc từng ticket.
- Review bị dời sang đầu Sprint kế tiếp khi chưa xong demo.
- Retrospective bị hủy ở những Sprint có nhiều lỗi.
- Một số PBIs được đánh dấu Done dù kiểm thử tích hợp còn thất bại.

### 16.2. Nhiệm vụ A – Nhận diện sai lệch (15 phút)

Với từng thực hành trên, hãy phân loại:
1. Vấn đề **timebox** hay **mục đích sự kiện**?
2. Vấn đề **cadence** hay **định nghĩa hoàn tất**?
3. Rủi ro gì đối với việc học từ phản hồi, chất lượng hoặc Sprint Goal?
4. Điều nào là quy định của Scrum, điều nào chỉ là lựa chọn lịch nội bộ?

Một nhóm trả lời tốt cần nhận ra:
- Planning sáu giờ cho Sprint hai tuần có thể quá dài và cần kiểm tra mục đích/hiệu quả, nhưng Scrum Guide **không đặt công thức cứng hai tuần bằng bốn giờ**.
- Daily 35 phút vi phạm timebox **15 phút**.
- Review dời tùy tiện và Retro bị hủy làm mất nhịp kiểm tra–thích ứng.
- Đánh dấu Done trước khi đáp ứng DoD là vấn đề chất lượng, không được hợp lý hóa bằng deadline.

### 16.3. Nhiệm vụ B – Lập lịch phù hợp (15 phút)

Thiết kế lịch Sprint hai tuần với:
- Sprint Planning vào đầu Sprint, đủ thời gian để xác định Why–What–How.
- Daily Scrum cố định 15 phút mỗi ngày làm việc.
- Review có stakeholder trước Retrospective, trong Sprint.
- Retrospective kết thúc Sprint, có thời gian chọn cải tiến cụ thể.
- Thời gian cho refinement và phối hợp kỹ thuật khi cần, không biến chúng thành sự kiện chính thức thứ sáu.

Ghi **ai cần tham gia**, mục đích, đầu vào và đầu ra mỗi sự kiện. Đưa ra lý do cho thời lượng đã chọn, không lấy số tối đa của Sprint một tháng làm lịch mặc định.

### 16.4. Nhiệm vụ C – Tính thời gian và điều chỉnh (10 phút)

Nhóm thử kế hoạch:
- Planning: 150 phút.
- Daily Scrum: 10 lần × 15 phút.
- Review: 90 phút.
- Retrospective: 60 phút.

Hãy tính tổng **thời lượng các phiên theo lịch**, và giải thích vì sao con số đó không phải “tổng giờ công tất cả thành viên” cũng không phải toàn bộ thời gian cộng tác.

**Đáp án kiểm tra:** 150 + 150 + 90 + 60 = **450 phút = 7,5 giờ** các phiên sự kiện. Nếu muốn tính giờ công tham dự, phải tính **ai thực sự tham gia mỗi phiên**, vì Daily Scrum dành cho Developers và thành phần các sự kiện khác không giống nhau.

### 16.5. Nhiệm vụ D – Xử lý một sự cố giữa Sprint (15 phút)

Ngày làm việc thứ sáu, hệ thống production gặp lỗi xác nhận hai người vào cùng một chỗ. Sự cố ảnh hưởng người dùng thật; Developers đang thực hiện story thông báo trạng thái.

Hãy mô tả:
1. Nhóm cần làm gì **ngay lập tức**, không chờ đến Review?
2. Daily Scrum dùng thế nào để nhìn thấy ảnh hưởng lên Sprint Goal?
3. Product Owner và Developers trao đổi thay đổi phạm vi ra sao?
4. Điều kiện nào chứng minh bản sửa đã an toàn, không làm giảm DoD?
5. Trong Review, nhóm nên thảo luận **tác động sản phẩm** nào?
6. Trong Retrospective, nhóm nên thảo luận **cải tiến cách làm việc** nào?
7. Khi nào mới có lý do cân nhắc hủy Sprint?

**Gợi ý:** bảo vệ người dùng và dữ liệu bằng quy trình ứng phó sự cố, minh bạch ảnh hưởng rồi điều chỉnh công việc. Chỉ cân nhắc hủy nếu Sprint Goal trở nên lỗi thời; không hủy chỉ để né báo cáo tiến độ xấu.

### 16.6. Nhiệm vụ E – Chọn một thử nghiệm cải tiến (10 phút)

Giả sử nhóm phát hiện Daily dài vì mọi người nêu các vấn đề debug chi tiết. Chọn một thay đổi cho Sprint tiếp theo:

> “Trong Daily, nêu ảnh hưởng đến Sprint Goal và chốt ai giải quyết sau; không debug ngay trước cả nhóm. Cuối Sprint, kiểm tra thời lượng Daily, thời gian hạng mục chờ xử lý và số lần nhóm phải gọi họp đột xuất.”

Nêu:
- Giả thuyết vì sao thay đổi này giúp.
- Dữ liệu nào xác nhận hoặc bác bỏ.
- Tác dụng phụ cần theo dõi (ví dụ các cản trở thật bị nói quá ngắn hoặc không được giải quyết sau Daily).
- Ai quan sát và khi nào xem lại.

### 16.7. Thang tự đánh giá

| Tiêu chí | Chưa đạt | Đạt | Vững |
| --- | --- | --- | --- |
| **Hiểu timebox** | Nhầm mức tối đa với thời lượng bắt buộc | Nêu đúng quy định Sprint và bốn sự kiện | Giải thích vì sao chọn timebox phù hợp và giới hạn của công thức |
| **Thiết kế cadence** | Họp tùy hứng, bỏ Review/Retro | Có lịch nhất quán đúng trình tự | Có phương án cho nghỉ lễ, phân tán và sự cố |
| **Mục đích sự kiện** | Mọi sự kiện đều báo status | Gắn Planning/Daily/Review/Retro với mục đích đúng | Tạo được quyết định thích ứng và liên kết artifacts |
| **Bảo vệ chất lượng** | Đánh dấu Done khi còn lỗi quan trọng | Tôn trọng DoD, minh bạch việc chưa xong | Chủ động giảm rủi ro, chia lát cắt và kiểm chứng sớm |
| **Cải tiến** | Chỉ đo số giờ họp | Chọn hành động Retro có mốc xem lại | Kết hợp flow, quality và outcome để đánh giá thay đổi |

## 17. Mẫu sử dụng ngay cho Scrum Team

### 17.1. Thẻ tổ chức sự kiện

~~~text
Sự kiện:
Mục đích kiểm tra hoặc thích ứng:
Timebox đã thống nhất:
Thời điểm và địa điểm / liên kết họp:
Ai cần tham gia:
Thông tin cần chuẩn bị:
Artifact hoặc mục tiêu liên quan:
Quyết định / hành động cần tạo:
Người cập nhật kết quả và nơi ghi:
Điều kiện kết thúc khi đã đạt mục đích:
~~~

### 17.2. Mẫu ghi kết quả Daily Scrum

~~~text
Sprint Goal:
Tiến triển đáng chú ý:
Hạng mục bị chặn / rủi ro cho mục tiêu:
Điều chỉnh ưu tiên hoặc kế hoạch hôm nay:
Ai sẽ trao đổi sâu sau Daily:
Mốc xác nhận kết quả:
Cần làm rõ với Product Owner?
~~~

Không cần bắt mọi người điền mẫu hàng ngày nếu bảng và trao đổi đã đủ minh bạch. Mẫu chỉ hỗ trợ khi nhóm thường quên quyết định sau Daily.

### 17.3. Mẫu quyết định sau Sprint Review

~~~text
Product Goal và Sprint Goal:
Increment đã đạt DoD:
Điều chưa đạt DoD và lý do:
Bằng chứng từ người dùng / stakeholder:
Bối cảnh sản phẩm đã thay đổi:
Giả thuyết được xác nhận hoặc bác bỏ:
Product Backlog cần thêm / bỏ / sắp lại:
Điều cần kiểm tra tiếp:
Người liên quan và mốc xem lại:
~~~

### 17.4. Mẫu thử nghiệm cải tiến từ Retrospective

~~~text
Vấn đề quan sát có bằng chứng:
Tác động đến chất lượng / hiệu quả / bền vững:
Giả thuyết nguyên nhân:
Thay đổi nhỏ sẽ thử:
Ai cùng thực hiện:
Thời điểm áp dụng:
Chỉ số hoặc quan sát để kiểm tra:
Tác dụng phụ cần theo dõi:
Ngày kiểm tra lại:
Quyết định: giữ / điều chỉnh / ngừng thử:
~~~

## 18. Checklist tổ chức sự kiện đúng mục đích và nhịp

**Thiết kế nhịp:**

- [ ] Sprint có độ dài cố định một tháng hoặc ngắn hơn và Sprint mới bắt đầu ngay sau Sprint trước.
- [ ] Các sự kiện Scrum còn lại được tổ chức trong Sprint theo đúng vai trò.
- [ ] Sprint Planning bắt đầu Sprint và làm rõ Why–What–How.
- [ ] Daily Scrum diễn ra 15 phút mỗi ngày làm việc, có cùng thời điểm và địa điểm phù hợp.
- [ ] Sprint Review diễn ra trước Retrospective và có cơ hội nhận phản hồi từ stakeholder.
- [ ] Sprint Retrospective kết thúc Sprint với một cải tiến có thể thực hiện.
- [ ] Thời lượng Planning/Review/Retro được chọn phù hợp Sprint, không mặc định dùng hết mức tối đa một tháng.
- [ ] Refinement được tổ chức khi giúp PBIs rõ hơn, không bị coi là sự kiện Scrum bắt buộc thứ sáu.

**Bảo đảm mục đích và trách nhiệm:**

- [ ] Sprint Planning tạo Sprint Goal và kế hoạch có thể thích ứng.
- [ ] Daily Scrum tập trung tiến triển Sprint Goal, không biến thành báo cáo cho quản lý.
- [ ] Những vấn đề dài được giải quyết sau Daily với đúng người liên quan.
- [ ] Sprint Review kiểm tra Increment, Product Goal và dữ liệu phản hồi, không chỉ demo.
- [ ] Sprint Retrospective xem cách làm việc, chất lượng và hiệu quả, không quy lỗi cá nhân.
- [ ] Developers lập kế hoạch thực hiện; Product Owner giúp làm rõ giá trị và ưu tiên; Scrum Master hỗ trợ Scrum hiệu quả.
- [ ] Các hạng mục chưa đạt DoD không bị báo cáo như Increment hoàn tất.
- [ ] Review không trở thành cổng bắt buộc trước khi phát hành Increment đã sẵn sàng.

**Thích ứng và học hỏi:**

- [ ] Việc khẩn được ứng phó theo mức nghiêm trọng thay vì chờ lịch họp định kỳ.
- [ ] Những thay đổi phạm vi được trao đổi minh bạch, bảo vệ Sprint Goal và chất lượng.
- [ ] Nhóm biết khi nào Sprint Goal còn khó đạt và khi nào thật sự đã trở nên lỗi thời.
- [ ] Có cách chuẩn bị cho nghỉ phép, ngày lễ hoặc múi giờ khác nhau mà không phá nhịp thường xuyên.
- [ ] Phản hồi từ Review được liên kết với thay đổi Product Backlog khi phù hợp.
- [ ] Hành động Retro có người phối hợp và mốc kiểm tra tác động ở Sprint tiếp theo.
- [ ] Nhóm đánh giá hiệu quả sự kiện qua **khả năng ra quyết định, dòng công việc, chất lượng và giá trị người dùng**, không chỉ qua số giờ họp.

**Kết luận:** Giới hạn thời gian giúp Scrum Team tập trung, còn nhịp sự kiện nhất quán tạo cơ hội thường xuyên để **minh bạch, kiểm tra và thích ứng**. Khi Planning trả lời được vì sao Sprint có giá trị, Daily hỗ trợ Developers điều chỉnh kế hoạch, Review giúp học từ Increment và stakeholder, Retrospective thúc đẩy cải tiến thực tế, nhóm không chỉ “họp đúng lịch” mà còn tiến gần Product Goal bằng phần mềm chất lượng, phản hồi sớm và khả năng giao hàng bền vững.
