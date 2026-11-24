# Tổ chức nhìn lại dựa trên sự kiện cùng điều kiện làm việc

> **Trọng tâm:** Nhìn lại (*retrospective*) trong Agile không phải cuộc họp để tìm người mắc lỗi, cũng không phải nghi thức hỏi “điều gì tốt, điều gì chưa tốt” rồi kết thúc bằng vài lời hứa. Một buổi nhìn lại hữu ích **dựa trên sự kiện có thể kiểm chứng, lắng nghe trải nghiệm của người tham gia và xem xét điều kiện hệ thống làm việc** để chọn một thay đổi nhỏ có thể thực hiện, đo phản hồi và học tiếp. Cần hiểu cả **điều đã xảy ra** lẫn **vì sao cách phối hợp, công cụ, hàng chờ, phụ thuộc và ràng buộc hiện tại** khiến kết quả ấy xuất hiện.

## 1. Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **sự kiện, dữ liệu quan sát, cảm nhận, giả thuyết về nguyên nhân, quyết định và kết quả cải tiến**.
2. Giải thích mục đích **Sprint Retrospective** trong Scrum và phân biệt nó với **Sprint Review, Daily Scrum, đánh giá hiệu suất cá nhân và hậu kiểm sự cố**.
3. Thu thập dữ liệu vừa đủ về **dòng công việc, chất lượng, hợp tác, tải công việc và phản hồi sản phẩm** mà không biến chỉ số thành công cụ đổ lỗi.
4. Tổ chức buổi nhìn lại an toàn về tâm lý, có sự tham gia của những người có góc nhìn khác nhau, kể cả nhóm phân tán.
5. Dựng **timeline sự kiện**, phân tích điều kiện làm việc và dùng **5 Whys, sơ đồ nhân–quả hoặc phân tích điểm nghẽn** một cách thận trọng.
6. Chọn tối đa một vài **thử nghiệm cải tiến có chủ sở hữu, phạm vi, điều kiện kiểm chứng và thời điểm xem lại**, thay vì tạo danh sách việc không ai làm.
7. Phân biệt việc **nhóm có thể tự thay đổi** với trở ngại cần Scrum Master, Product Owner hoặc bên ngoài hỗ trợ giải quyết.
8. Kết hợp cải tiến liên tục với **Scrum, Kanban, Lean, XP** và giữ **Definition of Done** cùng nhịp làm việc bền vững.
9. Đọc tình huống nền tảng học trực tuyến để đề xuất phương án giảm phát hiện lỗi muộn, WIP cao, phụ thuộc môi trường và làm thêm giờ.

## 2. Tình huống mở đầu: cùng một Sprint, nhiều lời giải thích

Một Scrum Team phát triển nền tảng học trực tuyến đặt **Sprint Goal**:

> “Người học có thể lưu và tiếp tục bài đầu trên thiết bị được hỗ trợ mà không nhận thông báo thành công sai.”

Kết thúc Sprint, nhóm có những quan sát **minh họa**:

- Có **12 Product Backlog Items (PBI)** được bắt đầu, **7 PBI** đạt Definition of Done.
- **3 PBI** bị chặn ở khâu tích hợp với API; **2 PBI** còn chờ review hoặc kiểm thử.
- Một kiểm thử tích hợp thất bại nhiều lần do dữ liệu thử bị dùng chung.
- Trong hai ngày cuối, một số thành viên làm thêm giờ để xử lý lỗi hồi quy.
- Sprint Review thu được phản hồi: luồng thành công dễ hiểu hơn, nhưng trường hợp mất mạng chưa được giải thích rõ với người học.

Sau Sprint, mọi người nói:

| Phát biểu | Điều được phản ánh | Điều còn cần làm rõ |
|---|---|---|
| “Developer không ước lượng tốt.” | Có cảm giác lượng việc cam kết vượt năng lực | Có bao nhiêu việc bị chặn bởi phụ thuộc, WIP và thay đổi phạm vi? |
| “QA nhận việc quá muộn.” | Công việc kiểm thử dồn ở cuối | Tại sao PBI tới bước kiểm thử muộn; có đủ lát cắt nhỏ để kiểm tra sớm? |
| “CI lúc nào cũng đỏ.” | Test hoặc tích hợp không đáng tin theo trải nghiệm nhóm | Lỗi nào là lỗi sản phẩm, lỗi môi trường, test flaky, hoặc thay đổi hợp đồng? |
| “Product Owner cứ đổi yêu cầu.” | Có cảm nhận về thay đổi và gián đoạn | Yêu cầu đổi gì, khi nào, nhằm mục tiêu nào và các bên đã trao đổi ra sao? |
| “Cứ phải làm thêm giờ mới giao được.” | Nhịp làm có dấu hiệu thiếu bền vững | Đây là tình huống đặc biệt hay lặp lại? Hàng chờ và năng lực thực tế thế nào? |

Nếu Scrum Master chỉ hỏi **“Ai làm sai?”**, nhóm sẽ phòng thủ và giấu thông tin. Nếu chỉ hỏi **“Mọi người cảm thấy thế nào?”** mà không xem sự kiện, cuộc họp có thể dừng ở cảm xúc nhưng không tìm được cơ chế cần cải thiện.

Một buổi nhìn lại tốt đặt câu hỏi:

> “Điều gì đã xảy ra, trong điều kiện nào, chúng ta có bằng chứng gì và có thể **thay đổi cách làm nào trong Sprint tiếp theo** để chất lượng lẫn khả năng đạt Sprint Goal tốt hơn?”

Điều này không phủ nhận trách nhiệm cá nhân về hành vi chuyên nghiệp. Nó giúp nhóm **xử lý hệ thống tạo ra vấn đề** thay vì dừng ở một cái tên.

## 3. Nền tảng: nhìn lại dựa trên thực nghiệm

### 3.1. Tách sáu lớp thông tin

| Lớp | Định nghĩa | Ví dụ | Cách dùng |
|---|---|---|---|
| **Sự kiện** | Điều có thể xác định đã xảy ra vào một thời điểm | “Ngày thứ 6, API test trả lỗi vì dữ liệu bị xung đột.” | Dựng lại diễn biến |
| **Số liệu quan sát** | Kết quả đo theo một định nghĩa rõ | “3 PBI đang chờ tích hợp khi Sprint kết thúc.” | Xem xu hướng, phạm vi và điểm nghẽn |
| **Trải nghiệm/cảm nhận** | Người tham gia đã trải qua và cảm nhận điều gì | “Tôi không dám đổi code vì sợ test vỡ.” | Tìm vấn đề ẩn và điều kiện cộng tác |
| **Giả thuyết nguyên nhân** | Giải thích có thể đúng, cần kiểm chứng | “Test dùng chung dữ liệu khiến pipeline đỏ khi chạy song song.” | Đề xuất kiểm tra hoặc thử nghiệm |
| **Quyết định cải tiến** | Thay đổi có chủ đích dựa trên thông tin hiện có | “Mỗi integration test tạo dữ liệu riêng.” | Thực thi thay đổi trong phạm vi kiểm soát |
| **Kết quả sau cải tiến** | Tín hiệu thu được sau thử nghiệm | “Lỗi test liên quan dữ liệu chung giảm.” | Giữ, sửa hoặc dừng cách làm |

Không nên chuyển **cảm nhận thành sự kiện** mà chưa kiểm chứng, nhưng cũng không được bác bỏ cảm nhận chỉ vì chưa có dashboard. Cảm nhận có thể là **tín hiệu sớm** về áp lực, quyền lực, bất định hoặc điều khó đo.

### 3.2. Minh bạch – kiểm tra – thích ứng

Scrum dựa trên **empiricism**: các quyết định hướng tới việc đã được quan sát và học từ kinh nghiệm. Ba trụ cột thường được nêu là:

1. **Transparency — Minh bạch:** người tham gia hiểu trạng thái thật của công việc và chuẩn chất lượng.
2. **Inspection — Kiểm tra:** xem sản phẩm và cách làm có tiến gần mục tiêu không, kịp thời phát hiện sai lệch.
3. **Adaptation — Thích ứng:** điều chỉnh khi phát hiện vấn đề hoặc có thông tin mới.

Một retrospective bỏ qua minh bạch **Definition of Done** hoặc dùng dữ liệu không nhất quán sẽ khó đưa ra cải tiến đúng. Một cuộc họp phân tích sắc sảo nhưng **không thử thay đổi nào** cũng chưa khép vòng thích ứng.

### 3.3. Nhìn lại là hoạt động học hỏi, không phải phiên tòa

Những điều nên có:

- Mô tả hành vi và điều kiện cụ thể, **không dán nhãn con người**.
- Cho phép **bất đồng có căn cứ**; an toàn tâm lý không có nghĩa tất cả phải đồng ý.
- Dùng dữ liệu để **hiểu hệ thống**, không xếp hạng nhân viên.
- Thừa nhận điều chưa biết, thay vì dựng một câu chuyện nguyên nhân duy nhất.
- Kết thúc bằng thay đổi **nằm trong khả năng hành động**, có cách kiểm tra tác dụng.

Một ngoại lệ quan trọng: hành vi quấy rối, lạm dụng, vi phạm bảo mật hoặc vấn đề nhân sự nghiêm trọng cần **kênh xử lý thích hợp**, không bị đánh đồng với “chỉ là vấn đề quy trình” hoặc buộc người bị ảnh hưởng phải kể chi tiết trước toàn nhóm.

## 4. Sprint Retrospective trong Scrum: mục đích và ranh giới

### 4.1. Sprint Retrospective kiểm tra điều gì?

Theo **Scrum Guide 2020**, mục đích của Sprint Retrospective là **lập kế hoạch các cách tăng chất lượng và hiệu quả**. Scrum Team xem Sprint vừa qua đối với:

- **Individuals:** cách các thành viên làm việc, học hỏi và phối hợp.
- **Interactions:** tương tác trong nhóm và với những bên liên quan.
- **Processes:** luồng tạo Increment, chính sách, hàng đợi và cách ra quyết định.
- **Tools:** CI, môi trường, công cụ quản lý, kiểm thử, giao tiếp.
- **Definition of Done:** cách áp dụng chuẩn chất lượng và những điểm cần cải thiện.

Nhóm thảo luận điều gì diễn ra tốt, vấn đề gặp phải và các điều kiện dẫn tới vấn đề. Sau đó **xác định những thay đổi có ích nhất để cải tiến**, giải quyết chúng càng sớm càng phù hợp; có thể đưa vào Sprint Backlog của Sprint tiếp theo.

**Scrum Team** chịu trách nhiệm cho sự kiện này. **Scrum Master** có trách nhiệm về hiệu quả Scrum Team và giúp các sự kiện tích cực, hiệu quả, đúng timebox, nhưng không nên độc quyền quyết định kết luận hoặc dùng cuộc họp để kiểm soát mọi người.

### 4.2. Timebox

Với Sprint một tháng, Scrum Guide quy định Sprint Retrospective **tối đa 3 giờ**; Sprint ngắn hơn thường dùng thời lượng ngắn hơn. Một nhóm Sprint hai tuần có thể chọn **60–90 phút minh họa**, tùy nhu cầu.

Không cần cố dùng đủ 3 giờ. Trái lại, khi một vấn đề quan trọng cần điều tra nhiều hơn, retrospective có thể **chọn hành động và người tiếp tục làm việc** thay vì cố giải quyết trọn sự cố kỹ thuật trong một buổi.

### 4.3. Sprint Retrospective khác Sprint Review và Daily Scrum thế nào?

| Hoạt động | Trọng tâm chính | Câu hỏi điển hình |
|---|---|---|
| **Daily Scrum** | Developers kiểm tra tiến độ hướng Sprint Goal và thích ứng Sprint Backlog | “Hôm nay điều chỉnh kế hoạch ra sao để tiến gần Sprint Goal?” |
| **Sprint Review** | Kiểm tra **Increment, kết quả sản phẩm và bối cảnh mới** cùng stakeholder; thích ứng Product Backlog | “Điều vừa giao tạo giá trị gì, feedback làm thay đổi ưu tiên nào?” |
| **Sprint Retrospective** | Kiểm tra **cách Scrum Team làm việc** và chọn cải tiến chất lượng/hiệu quả | “Điều kiện nào làm việc trôi hoặc tắc, ta sẽ thử thay đổi gì?” |
| **Incident/post-incident review** | Làm rõ và học từ **một sự cố cụ thể**, hỗ trợ phòng ngừa và phục hồi | “Lỗi xuất hiện, lan, được phát hiện/khôi phục qua những cơ chế nào?” |
| **Đánh giá hiệu suất cá nhân** | Hoạt động quản lý nhân sự theo quy trình riêng | Không nên ngụy trang thành retrospective của Scrum Team |

Các hoạt động có thể **trao đổi thông tin** nhưng không phải cùng một cuộc họp. Một lỗi mất dữ liệu có thể được điều tra trong incident review, rồi retrospective xem **cách cả nhóm giảm thời gian phát hiện hoặc cải thiện phối hợp**; không cần bắt mọi người kể lại dữ liệu nhạy cảm.

### 4.4. Không đợi cuối Sprint mới xử lý trở ngại

Agile khuyến khích học liên tục. Nếu CI đỏ, môi trường kiểm thử không hoạt động hoặc người học đang gặp lỗi nghiêm trọng, nhóm cần phản ứng **khi phát hiện**, không giữ mọi thứ tới Sprint Retrospective.

Retrospective là **điểm kiểm tra có cấu trúc để nhìn lại mẫu hình và cải tiến lâu dài**, không phải nơi duy nhất được phép nêu hoặc sửa vấn đề.

## 5. Điều kiện làm việc: tìm cơ chế thay vì gắn nhãn người

### 5.1. “Điều kiện làm việc” bao gồm những gì?

Trong phát triển phần mềm, điều kiện làm việc không chỉ là bàn ghế hoặc thiết bị. Nó gồm những yếu tố ảnh hưởng trực tiếp tới khả năng tạo Increment:

| Điều kiện | Câu hỏi kiểm tra | Ví dụ vấn đề |
|---|---|---|
| **Khối lượng và WIP** | Có quá nhiều việc mở cùng lúc không? | 12 PBI đang làm nhưng review chỉ xử lý 2 PBI/ngày |
| **Độ rõ yêu cầu** | Ví dụ nghiệp vụ, acceptance criteria và mục tiêu có đủ rõ? | “Lưu thành công” có nhiều cách hiểu |
| **Chất lượng kỹ thuật** | CI/test/refactoring có tạo phản hồi tin cậy không? | Integration test dùng chung dữ liệu, đỏ ngẫu nhiên |
| **Phụ thuộc bên ngoài** | Nhóm có quyền giải quyết hay phải chờ nhóm khác? | API đối tác đổi schema mà không có thông báo |
| **Năng lực và tri thức** | Có điểm phụ thuộc một người hoặc thiếu pairing? | Chỉ một người hiểu module xác thực |
| **Cấu trúc quyết định** | Ai có quyền ưu tiên, chấp nhận rủi ro và phê duyệt? | Một yêu cầu chen ngang không có người xác nhận |
| **Thời gian tập trung** | Có bị họp, yêu cầu gấp và chuyển ngữ cảnh quá nhiều? | Developer không có khoảng đủ dài chạy test và sửa lỗi |
| **Môi trường và công cụ** | Môi trường dev/test có đáng tin? | Dữ liệu test nhiễm chéo và tài khoản dùng chung |
| **Giao tiếp và múi giờ** | Thông tin quan trọng có đến đúng người? | Nhóm phân tán phải chờ nửa ngày cho một câu trả lời |
| **Nhịp làm bền vững** | Áp lực, on-call và làm thêm giờ có lặp lại? | Hai ngày cuối Sprint luôn phải cứu build |
| **An toàn tâm lý và tôn trọng** | Mọi người có thể nêu rủi ro mà không sợ bị phạt? | Test đỏ bị giấu để tránh bị quy trách nhiệm |
| **Hỗ trợ tổ chức** | Có quyền và nguồn lực giải quyết trở ngại hệ thống? | Không có quyền tạo môi trường test riêng |

Đừng giả định mọi điều kiện đều nằm trong quyền thay đổi của Scrum Team. Có thứ nhóm tự sửa được, có thứ cần **Scrum Master làm việc với tổ chức** hoặc Product Owner thương lượng ưu tiên/nguồn lực.

### 5.2. Phân tích theo công việc thật

Thay vì:

> “QA làm chậm tất cả.”

Đặt câu hỏi:

> “Khi nào PBI bắt đầu chờ kiểm thử? Trước đó đã có những thay đổi nào? Tại sao test chỉ chạy được sau khi toàn bộ nhánh UI–API hợp nhất? Có cách tạo lát cắt nhỏ và kết quả kiểm tra sớm hơn không?”

Thay vì:

> “Developer A thiếu trách nhiệm.”

Đặt câu hỏi:

> “Lỗi hồi quy được phát hiện ở đâu? Chúng ta có test, review, pairing, DoD và quyền thay đổi phù hợp không? Điều kiện nào khiến người viết code tưởng hành vi đã được kiểm chứng?”

**Câu hỏi hệ thống không xóa trách nhiệm cá nhân**; nó giúp tìm biện pháp phòng ngừa để nhóm không phụ thuộc vào việc mọi người luôn hoàn hảo.

### 5.3. Những yếu tố vừa nhân sự vừa kỹ thuật

Một nhóm làm thêm giờ vì “CI quá chậm” có thể đang đối mặt đồng thời:

- Test flaky gây chạy lại.
- PBI quá lớn và tích hợp muộn.
- Mỗi người sở hữu một module, khó chia việc review.
- Không có chính sách việc khẩn.
- Sprint Backlog không được điều chỉnh khi phát sinh thông tin mới.

Không nên chỉ đề xuất **nâng cấp máy CI** nếu nguyên nhân lớn là dữ liệu test nhiễm chéo và WIP cao. Cần kiểm tra **toàn luồng**.

## 6. Thu thập bằng chứng: dữ liệu định lượng và trải nghiệm

### 6.1. Bốn nhóm tín hiệu nên cân bằng

| Nhóm | Ví dụ | Câu hỏi học hỏi | Điều không chứng minh |
|---|---|---|---|
| **Dòng công việc** | WIP, throughput, cycle time, work item age, thời gian chờ review | Công việc bị tắc ở đâu và trong điều kiện nào? | Năng suất cá nhân hoặc giá trị sản phẩm |
| **Chất lượng** | Lỗi hồi quy, CI failure, flaky tests, sự cố, DoD chưa đạt | Sai lệch được phát hiện sớm hay muộn, có lặp lại? | Chắc chắn sản phẩm giải quyết đúng nhu cầu |
| **Cộng tác/điều kiện** | Phản hồi thành viên, làm thêm giờ, phụ thuộc, thời gian phản hồi | Có yếu tố hệ thống nào khiến nhóm khó tạo Increment? | Một cảm nhận đơn lẻ đại diện toàn nhóm |
| **Kết quả sản phẩm** | Lỗi người dùng, tỷ lệ tiếp tục bài, completion, phản hồi stakeholder | Cách làm có giúp tạo giá trị và tin cậy hơn? | Quan hệ nhân quả trực tiếp với một buổi retro |

**Nguyên tắc:** số liệu là **đầu vào cho hội thoại và thử nghiệm**, không phải bảng xếp hạng người hoặc “đích phải đẹp” bằng mọi giá.

### 6.2. Bốn phép đo Kanban thường gặp

**Work in Progress (WIP):** số work items đã bắt đầu nhưng chưa hoàn thành theo **Definition of Workflow** đã thống nhất.

**Throughput:** số work items hoàn thành trong một khoảng thời gian.

**Cycle time:** thời gian từ mốc bắt đầu tới mốc kết thúc của các work items đã hoàn thành.

**Work item age:** thời gian một work item **đang mở** đã trải qua kể từ mốc bắt đầu.

Ví dụ một bảng công việc minh họa:

| PBI | Ngày bắt đầu | Trạng thái tại cuối Sprint | Diễn giải |
|---|---|---|---|
| LEARN-31 | Ngày 1 | Done ngày 5 | Cycle time 4 ngày theo cách tính thời điểm nêu trong ví dụ |
| LEARN-32 | Ngày 2 | Done ngày 9 | Cycle time 7 ngày |
| LEARN-33 | Ngày 3 | Đang chờ API ở ngày 10 | Work item age 7 ngày; **không phải cycle time đã hoàn thành** |
| LEARN-34 | Ngày 4 | Đang chờ review ở ngày 10 | Work item age 6 ngày; chưa Done |

**Lưu ý:** phép tính ngày ở bảng là minh họa theo khoảng cách giữa các mốc ngày; dữ liệu thực phải định nghĩa rõ mốc thời gian, ngày nghỉ và cách làm tròn. Nếu một PBI chờ lâu, điều quan trọng là **vì sao luồng tạo giá trị bị chặn**, không phải ai “giữ thẻ” trên bảng.

### 6.3. Dữ liệu Scrum: không dùng story points để xếp hạng

Scrum không bắt buộc dùng story points hoặc velocity. Nếu đội dùng velocity để hỗ trợ dự báo, hãy tránh:

- So velocity giữa các đội với thang ước lượng khác nhau.
- Dùng số điểm hoàn thành làm KPI hiệu suất cá nhân.
- Tăng điểm để báo “năng suất tăng”.
- Đếm PBI chưa đạt Definition of Done thành Done.

Một retro có thể nhìn **khả năng đạt Sprint Goal, tính minh bạch Increment, lượng việc chờ và rủi ro** thay vì chỉ so tỷ lệ “cam kết/kết quả”.

### 6.4. Dữ liệu CI và chất lượng

Các câu hỏi hữu ích:

- Build đỏ do **lỗi sản phẩm, lỗi test, môi trường hay dependency**?
- Thời gian từ commit tới **kết quả đủ tin cậy để hành động** là bao lâu?
- Có kiểm thử nào thường đỏ khi chạy song song nhưng qua khi chạy riêng?
- Lỗi hồi quy được phát hiện ở **unit, contract, integration, E2E hay production**?
- Các bước kiểm tra bắt buộc của **Definition of Done** có được hoàn tất trước khi đánh dấu Done?

Đừng xem số lần CI đỏ tăng luôn là xấu: khi mới bổ sung kiểm tra có giá trị, đội có thể phát hiện thêm lỗi vốn từng lọt tới production. Điều cần xem là **chất lượng, tốc độ xử lý và xu hướng theo bối cảnh**.

### 6.5. Dữ liệu định tính: hỏi người trải nghiệm công việc

Một bộ câu hỏi mở:

- “Tình huống nào trong Sprint giúp bạn hoàn thành việc dễ hơn?”
- “Ở thời điểm nào bạn phải chờ hoặc bị gián đoạn lâu nhất?”
- “Có việc nào bạn ngại báo sớm? Điều gì khiến bạn ngại?”
- “Điều kiện nào khiến review hoặc kiểm thử khó diễn ra sớm?”
- “Quyết định hay thông tin nào đến quá muộn?”
- “Nếu thay **một** điều trong cách làm, điều gì có khả năng giúp nhiều nhất?”

Phản hồi nên được xem với tinh thần **tôn trọng và không phán xét**. Khi vấn đề liên quan quyền lực, nhân sự hoặc bảo mật, có thể cần thu thập qua kênh phù hợp hơn, tránh công khai chi tiết nhạy cảm trước cả nhóm.

### 6.6. Kiểm tra chất lượng dữ liệu

Trước khi rút kết luận:

1. Các giai đoạn được so có **cùng cách định nghĩa Done, bắt đầu và loại PBI** không?
2. Có thay đổi cách ghi sự kiện hoặc công cụ khiến số liệu không so sánh được?
3. Số mẫu có đủ cho kết luận hay chỉ là vài việc đặc biệt?
4. Có PBI bị chia nhỏ, chuyển cột hoặc giấu ngoài bảng để làm chỉ số đẹp?
5. Mức tác động lỗi có được phân biệt hay mọi bug được đếm giống nhau?
6. Điều gì **không có trong dữ liệu**: công việc hỗ trợ, thời gian điều tra, chuyển ngữ cảnh, phát hiện sớm vấn đề?

Không cần chờ dữ liệu hoàn hảo mới cải tiến, nhưng phải minh bạch về **giới hạn của bằng chứng**.

## 7. Chuẩn bị một buổi nhìn lại có ích

### 7.1. Xác định mục tiêu của buổi nhìn lại

Không phải lúc nào cũng cần nhìn mọi vấn đề trong một buổi. Với một Sprint có nhiều sự cố tích hợp, có thể đặt câu hỏi trọng tâm:

> “Những điều kiện nào khiến lỗi tích hợp phát hiện muộn và PBI bị chặn ở cuối Sprint, và thay đổi nào giúp chúng ta phát hiện sớm hơn mà vẫn bảo vệ chất lượng?”

Mục tiêu đủ cụ thể sẽ giúp nhóm chuẩn bị **dữ liệu liên quan**, thay vì mở 20 dashboard mà không biết muốn học gì.

Tuy nhiên, nên để chỗ cho người tham gia nêu vấn đề quan trọng mà người điều phối chưa dự đoán được.

### 7.2. Chuẩn bị bằng chứng trước buổi họp

Một tập tài liệu **vừa đủ** có thể gồm:

- Sprint Goal và điều đã thực sự đạt; những PBI đạt/chưa đạt **Definition of Done**.
- Timeline một vài sự kiện quan trọng: API thay hợp đồng, CI lỗi, môi trường gián đoạn, thay đổi phạm vi.
- Ảnh chụp bảng Kanban hoặc dữ liệu WIP/work item age/cycle time.
- Lỗi hồi quy/sự cố được xác minh và thời điểm phát hiện.
- Kết luận từ Sprint Review hoặc phản hồi người dùng **liên quan cách làm**, không trộn toàn bộ backlog vào retro.
- Những trở ngại do thành viên ghi nhận và những việc cải tiến từ retro trước.

Nên **ẩn tên hoặc chi tiết không cần thiết** nếu làm như vậy giúp thảo luận an toàn hơn; dữ liệu sự cố/bảo mật cần xử lý theo quyền truy cập và chính sách.

Không chuẩn bị slide dài chỉ để chứng minh nhóm đã có hoạt động cải tiến. Hãy đưa **câu hỏi và bằng chứng** tới gần người cần thảo luận.

### 7.3. Mời đúng người và bố trí quyền tham gia

Trong Scrum, **Scrum Team** là người tham gia Sprint Retrospective. Có thể mời chuyên gia hoặc đại diện bên ngoài vào phần trao đổi cụ thể **nếu nhóm thấy hữu ích và có cách bảo đảm sự cởi mở**, nhưng không biến sự kiện thành phiên chất vấn trước lãnh đạo.

Những tình huống cần cân nhắc:

- Nhóm có người mới, người ít nói hoặc ít quyền lực: bắt đầu bằng **viết ý kiến im lặng** giúp giảm áp lực phải tranh lời.
- Có mâu thuẫn giữa hai chức năng: điều phối dựa trên **quy trình và bằng chứng**, không để người có chức danh cao quyết định lời kể.
- Có vấn đề nhân sự nhạy cảm: sử dụng kênh riêng phù hợp thay vì ép nêu trước cả nhóm.
- Có nhóm phân tán: chuẩn bị công cụ bảng chung, múi giờ và cách thu ý kiến bất đồng bộ.

### 7.4. Một agenda 90 phút minh họa

| Khoảng thời gian | Hoạt động | Đầu ra |
|---|---|---|
| **0–10 phút** | Mở đầu, nhắc mục tiêu, an toàn tâm lý, kiểm tra hành động retro trước | Mọi người hiểu phạm vi và cách trao đổi |
| **10–25 phút** | Thu thập sự kiện, dữ liệu, trải nghiệm: viết im lặng rồi nhóm theo chủ đề | Timeline và các tín hiệu chính |
| **25–45 phút** | Khám phá điều kiện và giả thuyết nguyên nhân; hỏi điều gì còn thiếu | Một vài giả thuyết có thể kiểm chứng |
| **45–65 phút** | So sánh các can thiệp khả thi và chọn 1–2 thử nghiệm | Thay đổi ưu tiên và lý do |
| **65–80 phút** | Viết thẻ thử nghiệm: người phối hợp, phạm vi, tín hiệu, guardrail, điểm xem lại | Hành động đủ cụ thể để thực thi |
| **80–90 phút** | Chốt trách nhiệm, kiểm tra cảm nhận và cách tiếp tục theo dõi | Cam kết và cách khép vòng học |

Đây là agenda **tùy chỉnh**, không phải thời lượng bắt buộc. Với Sprint ngắn hoặc dữ liệu ít, có thể rút gọn; với vấn đề phức tạp, chọn một nhóm nhỏ điều tra tiếp theo quyền hạn thích hợp.

### 7.5. Năm giai đoạn điều phối dễ nhớ

Một khung phổ biến trong thực hành retrospective:

1. **Set the Stage — Tạo điều kiện:** mục tiêu, bối cảnh, cách trao đổi an toàn.
2. **Gather Data — Thu thập dữ liệu:** sự kiện, số liệu, trải nghiệm và góc nhìn.
3. **Generate Insights — Tạo hiểu biết:** phân biệt mẫu hình, điều kiện và giả thuyết.
4. **Decide What to Do — Chọn hành động:** xác định cải tiến có tác động và có thể làm.
5. **Close — Kết thúc:** phân công, kiểm tra chất lượng buổi họp, mốc xem lại.

Đây là **khung facilitation có thể tham khảo**, không phải năm Scrum Events hay một quy tắc Scrum bắt buộc.

### 7.6. Một lời mở đầu giúp mọi người trao đổi tốt hơn

Người điều phối có thể nói:

> “Chúng ta không có mục tiêu xác định ai yếu kém. Hãy bắt đầu từ những điều đã quan sát được và trải nghiệm thật, phân biệt điều đã xác minh với giả thuyết. Khi nói về sự cố, hãy hỏi điều kiện nào khiến nó dễ xảy ra hoặc khó phát hiện. Cuối buổi, chúng ta chọn một thay đổi vừa đủ, có cách kiểm tra tác dụng và không che giấu rủi ro chất lượng.”

Lời mở đầu chỉ có ích nếu **hành vi thực tế phù hợp**: khi ai đó đưa vấn đề khó ra, nhóm phải lắng nghe và xử lý công bằng. Đọc một tuyên bố “an toàn” nhưng sau đó trách phạt người nêu lỗi sẽ khiến lần sau thông tin bị giấu.

## 8. Từ dữ liệu thô tới timeline sự kiện

### 8.1. Vì sao timeline quan trọng?

Trong một Sprint nhiều việc chồng chéo, người tham gia nhớ khác nhau. Người viết UI có thể nhớ “API đổi phút chót”, còn người viết API nhớ “yêu cầu chưa rõ từ ngày đầu”.

Timeline giúp đưa cuộc thảo luận từ **ấn tượng tổng quát** về **các mốc cụ thể**:

| Mốc trong Sprint | Sự kiện xác minh được | Điều kiện kèm theo | Câu hỏi cần tìm hiểu |
|---|---|---|---|
| Ngày 1 | Sprint Planning chọn luồng lưu tiến độ | Một số trạng thái lỗi chưa có ví dụ chấp nhận | Vì sao rủi ro timeout chưa được làm rõ? |
| Ngày 2 | UI và API bắt đầu song song | Contract mới ở dạng trao đổi miệng | Có thể viết contract test sớm hơn không? |
| Ngày 4 | API bổ sung trạng thái lỗi | Người phụ trách UI bận việc khác; WIP cao | Thông tin thay đổi đã tới consumer thế nào? |
| Ngày 6 | CI tích hợp đỏ nhiều lần | Hai test dùng cùng tài khoản thử | Dữ liệu thử có thể cô lập theo test không? |
| Ngày 8 | Nhiều PBI chuyển tới review và QA | Bắt đầu nhiều việc nhưng ít PBI kết thúc | WIP limit/chia lát cắt có phù hợp? |
| Ngày 9 | Lỗi thông báo thành công giả được tìm thấy | Một số test chỉ có happy path | Tầng test nào có thể phát hiện sớm? |
| Ngày 10 | 7 PBI đạt DoD, 5 PBI chưa đạt | Thành viên làm thêm giờ | Cần điều chỉnh kế hoạch và nhịp làm ra sao? |

**Sự kiện minh họa** không khẳng định có một nguyên nhân duy nhất. Timeline tạo khung để phân tích các cơ chế hỗ trợ hoặc cản trở.

### 8.2. Viết thẻ sự kiện rõ ràng

Mẫu thẻ:

~~~text
ID: EVT-06
Thời điểm: Ngày 6 của Sprint
Điều quan sát được:
  CI integration test thất bại ở môi trường thử khi chạy song song.
Nguồn bằng chứng:
  Kết quả pipeline và dữ liệu thử được phép truy cập.
Tác động:
  PBI không thể hoàn tất kiểm tra; review bị chờ.
Điều kiện liên quan:
  Nhiều test dùng cùng tài khoản và cùng sửa trạng thái.
Điều chưa biết:
  Tỷ lệ thất bại do dữ liệu chồng chéo so với lỗi sản phẩm thật.
Người có thể hỗ trợ làm rõ:
  Developers/Tester phụ trách môi trường và tích hợp.
~~~

Mẫu này giúp tránh các nhãn chung như “CI rất tệ”, đồng thời không biến retrospective thành hồ sơ truy trách nhiệm cá nhân.

### 8.3. Sử dụng mốc tích cực, không chỉ mốc lỗi

Một timeline chỉ có thất bại dễ khiến nhóm nghĩ mọi thứ đều tệ. Cũng nên xem:

- Một lần pairing giúp giải quyết lỗi nhanh.
- PBI được chia nhỏ thành một lát cắt dọc và đạt Done sớm.
- Phản hồi Product Owner giúp sửa cách hiểu trước khi code.
- Một kiểm thử hợp đồng phát hiện hồi quy trước merge.
- Một ngày nhóm **giảm WIP và cùng hỗ trợ việc gần Done**.

Câu hỏi hữu ích: **“Điều kiện nào đã giúp việc tốt xảy ra và có thể duy trì chúng?”** Cải tiến không chỉ là sửa lỗi; còn là củng cố năng lực đang có.

### 8.4. Gắn cảm nhận vào thời điểm thay vì tranh luận chung

Ví dụ:

> “Tôi thấy căng thẳng từ ngày 8 vì có ba PBI cần review trong khi tôi vẫn xử lý sự cố CI.”

Phát biểu này có thể kiểm tra với work item age, lịch on-call và tiến độ review. Điều quan trọng là **hiểu điều kiện tạo áp lực**, không tranh luận xem người đó “có quyền cảm thấy căng” hay không.

**Không bắt buộc mọi trải nghiệm cá nhân phải được chứng minh bằng số liệu.** Có những rủi ro về hành vi tổ chức, tin tưởng và an toàn tâm lý cần tiếp nhận một cách tôn trọng, với kênh bảo vệ phù hợp.

## 9. Phân tích nguyên nhân mà không quy kết cá nhân

### 9.1. “Nguyên nhân gốc” thường là một mạng điều kiện

Một lỗi xảy ra trong hệ thống phần mềm có thể do nhiều điều kiện cùng xuất hiện:

- Hành vi nghiệp vụ chưa được làm rõ.
- Test chỉ bảo vệ đường thành công.
- Đổi API không được thông báo cho consumer.
- CI không đáng tin, nên nhóm mất niềm tin vào báo đỏ.
- WIP cao khiến việc review/test dồn cuối.
- Lịch phát hành tạo áp lực và giảm thời gian kiểm chứng.

Không nên ép mọi vấn đề vào một “root cause” duy nhất nếu bằng chứng cho thấy nhiều nguyên nhân tương tác.

### 9.2. Dùng 5 Whys như công cụ đặt câu hỏi

**Vấn đề:** kiểm thử tích hợp thường thất bại khi chạy song song.

| Câu hỏi | Trả lời giả định | Điều cần xác minh |
|---|---|---|
| **Vì sao 1:** tại sao test đỏ khi chạy song song? | Hai test cùng sửa dữ liệu tiến độ của một tài khoản | Log và dữ liệu thử có xác nhận không? |
| **Vì sao 2:** vì sao cùng một tài khoản? | Thiết lập test mặc định một tài khoản dùng chung | Có test nào tạo dữ liệu riêng không? |
| **Vì sao 3:** vì sao không cô lập dữ liệu? | Test helper hiện tại không có cơ chế tạo/xóa tài khoản riêng | Chi phí tạo và dọn dữ liệu là gì? |
| **Vì sao 4:** vì sao helper chưa được cải thiện? | Nhóm ưu tiên giao feature; không có ai nhận trách nhiệm cải thiện hạ tầng thử | Việc này có được nhìn thấy trong backlog không? |
| **Vì sao 5:** vì sao chưa có cơ chế phản ứng với test flaky lặp lại? | Chưa có chính sách và tín hiệu theo dõi độ ổn định CI | Ai có thể giúp thiết lập và duy trì chính sách? |

Đây là **giả thuyết phân tích**, không được kết luận chỉ bằng chuỗi câu hỏi. Các câu trả lời phải được **đối chiếu bằng bằng chứng**.

**Bẫy thường gặp:** hỏi 5 Whys để rồi kết thúc ở “vì Developer bất cẩn”. Điều đó không giải thích tại sao quy trình không phòng ngừa hoặc phát hiện được lỗi và không tạo cải tiến bền vững.

### 9.3. Sơ đồ nguyên nhân–điều kiện

~~~mermaid
flowchart TD
    O["Kết quả: lỗi tích hợp phát hiện muộn, PBI chờ lâu"] --> U["Yêu cầu chưa rõ"]
    O --> T["CI / test chưa đáng tin"]
    O --> W["WIP và kích thước PBI cao"]
    O --> D["Phụ thuộc API và review"]
    O --> S["Áp lực thời gian cuối Sprint"]

    U --> AC["Thiếu ví dụ thất bại / timeout"]
    T --> DB["Dùng chung dữ liệu test"]
    W --> Q["Nhiều PBI mở, ít việc Done"]
    D --> C["Hợp đồng API xác nhận muộn"]
    S --> L["Làm thêm giờ, dễ bỏ qua kiểm chứng"]
~~~

Sơ đồ thể hiện **những nhánh cần kiểm tra**, không khẳng định có bằng chứng cho mọi mũi tên. Nhóm nên đánh dấu rõ:

- **Đã xác minh:** có log, timeline, dữ liệu hoặc nhiều nguồn nhất quán.
- **Có khả năng:** giải thích hợp lý nhưng cần thử nghiệm/điều tra thêm.
- **Chưa rõ:** hiện không đủ thông tin.

### 9.4. Phân biệt triệu chứng với điều kiện tạo triệu chứng

Ví dụ:

| Triệu chứng | Giả thuyết điều kiện | Một can thiệp khả thi |
|---|---|---|
| “Review muộn.” | PBI lớn, nhiều người bắt đầu việc đồng thời | WIP limit và lát cắt dọc nhỏ |
| “CI đỏ liên tục.” | Test dùng dữ liệu chung hoặc assertion theo timing | Cô lập dữ liệu và điều kiện chờ dựa trên trạng thái |
| “Làm thêm giờ.” | Kế hoạch không thích ứng khi phụ thuộc kéo dài | Minh bạch năng lực, điều chỉnh phạm vi và chính sách gián đoạn |
| “Bug production lọt qua.” | Acceptance criteria thiếu trường hợp lỗi; integration test muộn | Làm rõ ví dụ sớm, test ở ranh giới phù hợp |
| “Chỉ một người sửa được module.” | Tri thức tập trung và thiếu lưới test an toàn | Pairing luân phiên, test, refactoring và quyền phù hợp |

**Không được hứa** rằng mỗi can thiệp chắc chắn giải quyết vấn đề. Đó là các giả thuyết cần theo dõi kết quả.

### 9.5. Tránh lạm dụng công cụ phân tích

5 Whys, fishbone, causal-loop diagram hoặc timeline đều chỉ là **công cụ hỗ trợ hội thoại**. Chọn cách đơn giản nhất đáp ứng vấn đề:

- Lỗi test đã rõ nguyên nhân: có thể **sửa ngay và ghi bài học ngắn**.
- Vấn đề lặp nhiều Sprint, nhiều nhóm và không rõ nguyên nhân: cần **timeline và phân tích hệ thống**.
- Có xung đột nghiêm trọng hoặc quyền lực ảnh hưởng: cần **người điều phối phù hợp** và có thể cần kênh riêng.
- Có nguy cơ an toàn/bảo mật: đi theo **quy trình ứng cứu và điều tra được phép**, không đăng chi tiết nhạy cảm lên bảng retro công khai.

Đừng để cuộc họp phân tích dài thay thế hành động bảo vệ người dùng hoặc sửa lỗi có bằng chứng rõ.

## 10. Chọn thử nghiệm cải tiến thay vì tạo danh sách lời hứa

### 10.1. Một hành động retro tốt có hình dạng nào?

Một câu yếu:

> “Cần giao tiếp tốt hơn và test sớm hơn.”

Câu có thể thực thi:

> “Trong hai Sprint tiếp theo, với các PBI thay đổi API lưu tiến độ, Developers và Tester sẽ làm rõ tối thiểu một ví dụ đường thành công và một ví dụ lỗi trước khi hiện thực; một contract test phù hợp chạy trong CI trước merge. Cuối mỗi Sprint xem lại số PBI bị chặn do sai hợp đồng, thời gian phản hồi CI và lỗi lọt tới người học.”

Câu thứ hai có **phạm vi, hành vi cụ thể, thời gian, người phối hợp, bằng chứng và điều kiện xem lại**.

### 10.2. Thẻ thử nghiệm cải tiến

~~~yaml
# Minh họa; không phải schema công cụ quản lý bắt buộc.
experiment_id: RETRO-EXP-02
problem: "PBI API thường chờ kiểm thử tích hợp tới cuối Sprint"
observations:
  - "Ba PBI đang chờ API ở cuối Sprint gần nhất"
  - "Có lỗi CI liên quan test dùng chung dữ liệu"
hypothesis: >
  Nếu PBI được chia nhỏ hơn, test có dữ liệu riêng và kiểm tra contract
  chạy sớm, thời gian chờ tích hợp và lỗi phát hiện muộn sẽ giảm.
action:
  - "Mỗi integration test quan trọng tạo dữ liệu riêng"
  - "Kiểm tra hợp đồng API trước merge cho các thay đổi liên quan"
scope: "Luồng lưu tiến độ trong hai Sprint thử nghiệm"
facilitator: "Scrum Master hỗ trợ gỡ trở ngại"
implementation_owners: "Developers cùng người có chuyên môn kiểm thử"
product_alignment: "Product Owner xác nhận ưu tiên giảm rủi ro lưu tiến độ"
signals:
  - "Work item age ở bước tích hợp"
  - "Số PBI bị chặn bởi sai hợp đồng"
  - "Độ ổn định và thời gian phản hồi CI"
guardrails:
  - "Không bỏ qua kiểm tra bắt buộc trong Definition of Done"
  - "Không tăng lỗi ảnh hưởng người học sau phát hành"
review_point: "Sprint Retrospective sau hai Sprint thử nghiệm"
decision_options: ["Giữ", "Điều chỉnh", "Dừng"]
~~~

**Không cần mọi retro có file YAML**. Có thể ghi vào một PBI cải tiến hoặc Sprint Backlog; điều quan trọng là người phù hợp thấy nó và theo dõi được.

### 10.3. Chọn 1–2 thay đổi đáng thử

Một retro có thể khám phá mười vấn đề, nhưng nếu cam kết sửa cả mười, nhóm dễ **làm thêm việc cải tiến trên nền WIP đã cao**. Chọn ít hạng mục:

- Có ảnh hưởng đáng kể đến chất lượng hoặc Sprint Goal.
- Có bằng chứng hoặc giả thuyết đủ rõ để thử.
- Nằm trong tầm thay đổi hoặc có người có thẩm quyền hỗ trợ.
- Phạm vi đủ nhỏ để triển khai và nhận phản hồi sớm.
- Có tín hiệu đánh giá mà không tạo thủ tục quá nặng.

**Dot voting** hoặc một khung chấm điểm có thể giúp ưu tiên chủ đề thảo luận, nhưng ý kiến đa số không tự phủ quyết **rủi ro an toàn, pháp lý hoặc vấn đề quyền lực nghiêm trọng**.

### 10.4. Phân biệt hạng mục trong quyền nhóm với trở ngại cần hỗ trợ

| Loại | Ví dụ | Cách xử lý |
|---|---|---|
| **Nhóm tự đổi được** | Chia PBI nhỏ, đặt WIP limit phù hợp, ghép cặp khi review | Thử trong Sprint kế tiếp và theo dõi |
| **Cần Product Owner** | Dành năng lực cho cải thiện chất lượng thay vì tính năng mới | Minh bạch chi phí cơ hội và liên hệ Product Goal |
| **Cần Scrum Master/tổ chức** | Xin quyền tạo môi trường test hoặc giải quyết phụ thuộc giữa đội | Scrum Master hỗ trợ tháo gỡ trở ngại, theo dõi quyết định |
| **Cần chuyên gia/chính sách** | Thay đổi kiểm soát bảo mật, quyền truy cập, dữ liệu thử | Tham vấn và tuân thủ thẩm quyền phù hợp |
| **Vượt quyền nhóm, chưa có lời giải** | Chính sách phân bổ công việc nhiều nhóm gây gián đoạn | Ghi bằng chứng, đề xuất thử nghiệm/đàm phán, cập nhật trạng thái |

Một nhóm không thể tự cấp quyền hạ tầng **không nên bị đánh giá là thiếu cải tiến** chỉ vì trở ngại phụ thuộc quyết định bên ngoài. Trách nhiệm của nhóm là **minh bạch, đề xuất và phối hợp**, không giả vờ có quyền quyết định.

### 10.5. Gắn thử nghiệm với công việc thực tế

Trong Scrum, những cải tiến có tác động có thể được đưa vào **Sprint Backlog của Sprint kế tiếp**. Không phải “sản phẩm phụ” không có thời gian làm.

Ví dụ:

- Tạo test helper cô lập dữ liệu: cần effort và người thực hiện.
- Thêm contract test cho API: cần code, review và CI.
- Thử WIP limit: cần thay đổi chính sách pull và cùng thực hiện.
- Làm rõ acceptance criteria: cần Product Owner và Developers phối hợp.

Nếu nhóm không cân nhắc năng lực, các hành động retro dễ thành **việc vô hình ngoài giờ**, đi ngược sustainable pace.

### 10.6. Đo kết quả, không chỉ đánh dấu “đã làm”

“Đã thêm 10 tests” là **output**. Câu hỏi hiệu quả hơn:

- Các PBI còn chờ tích hợp lâu như trước không?
- Lỗi sai hợp đồng còn lọt qua CI không?
- Thời gian phản hồi build có còn phù hợp không?
- Người dùng có gặp ít lỗi liên quan hơn không?
- Đội có còn phải làm thêm giờ để hoàn tất DoD không?

Một thử nghiệm có thể **thực hiện đúng kế hoạch nhưng không cải thiện kết quả**. Khi đó nên học và đổi cách tiếp cận, không nhất thiết quy kết người thực hiện thất bại.

## 11. Cấu trúc vòng cải tiến: từ retro tới Sprint tiếp theo

### 11.1. Minh họa chu trình

~~~mermaid
flowchart TD
    A["Sprint: sự kiện, công việc, Increment, phản hồi"] --> B["Retrospective: thu thập dữ liệu"]
    B --> C["Khám phá điều kiện và giả thuyết"]
    C --> D["Chọn 1–2 thử nghiệm cải tiến"]
    D --> E["Đưa vào kế hoạch và phân bổ năng lực"]
    E --> F["Thực hiện, quan sát, xử lý blocker"]
    F --> G["Kiểm tra tác dụng và guardrails"]
    G --> H{"Giữ, sửa hay dừng?"}
    H -->|"Giữ"| I["Chuẩn hóa cách làm hiệu quả"]
    H -->|"Sửa / dừng"| J["Điều chỉnh giả thuyết và thử nghiệm"]
    I --> A
    J --> A
~~~

Điểm yếu của nhiều retro là **đứt đoạn giữa D và F**: nhóm nêu cải tiến rất tốt nhưng không phân bổ thời gian hoặc người thực hiện.

### 11.2. Hành động nhỏ nhưng có điều kiện thành công

Một số ví dụ:

| Vấn đề | Thử nghiệm nhỏ | Tín hiệu | Guardrail |
|---|---|---|---|
| Review dồn cuối Sprint | Với PBI liên quan API, ghép cặp review thay đổi nhỏ trong ngày | Work item age ở review, số PBI đạt DoD | Không làm tăng lỗi sau phát hành |
| CI đỏ vì test flaky | Tạo dữ liệu riêng cho nhóm integration tests rủi ro | Tần suất lỗi không tái hiện, thời gian CI | Không tắt test quan trọng |
| PBI quá lớn | Chia các PBI đầu Sprint thành lát dọc có thể kiểm chứng | Cycle time, số việc đang mở | Giữ giá trị và acceptance criteria |
| Lỗi UI–API phát hiện muộn | Thảo luận ví dụ trạng thái lỗi, thêm contract test trước merge | Lỗi contract và thời gian phát hiện | Không xây test giòn bám chi tiết |
| Nhiều yêu cầu chen ngang | Thử chính sách lớp dịch vụ và minh bạch chi phí cơ hội | Số lần gián đoạn, work item age | Không bỏ xử lý sự cố khẩn thật |
| Thành viên quá tải | Hạn chế WIP, luân phiên hỗ trợ phần gần Done | Làm thêm giờ, cảm nhận tải, thời gian chờ | Không áp chỉ tiêu cá nhân gây áp lực |

Không thể chọn mức WIP hoặc thời lượng pairing “chuẩn” cho mọi nhóm. Cần thỏa thuận phù hợp với rủi ro, năng lực, loại việc và kiểm tra kết quả.

### 11.3. Theo dõi giữa Sprint mà không mở thêm một nghi thức

Hành động cải tiến nên xuất hiện ở nơi nhóm **đã nhìn công việc**:

- Một PBI kỹ thuật hoặc item cải tiến trong Sprint Backlog.
- Một quy tắc làm việc được cập nhật trên board.
- Một kiểm tra CI được thêm và xem kết quả khi chạy.
- Một mục ngắn trên bảng trở ngại có người theo dõi.

Trong Daily Scrum, Developers có thể kiểm tra xem trở ngại đang ảnh hưởng Sprint Goal thế nào, không cần biến sự kiện thành phiên báo cáo trạng thái hành động retro cho quản lý.

### 11.4. Xem lại sau thử nghiệm

Với mỗi thử nghiệm, nhóm hỏi:

1. Hành động **đã được thực hiện đúng phạm vi** chưa?
2. Dữ liệu thay đổi thế nào, có đủ mẫu và cùng định nghĩa không?
3. Có tác động bất lợi tới chất lượng hoặc người dùng không?
4. Những yếu tố khác nào đồng thời thay đổi?
5. Người tham gia **cảm thấy điều kiện làm việc** tốt hơn hay xấu hơn? Vì sao?
6. Nên **giữ, mở rộng, điều chỉnh, dừng hoặc thử lại giả thuyết khác**?

Đó là cách retrospective trở thành **chu trình cải tiến liên tục**, không phải cuộc họp độc lập lặp lại mỗi Sprint.

## 12. Case study: từ Sprint chật vật tới thay đổi điều kiện làm việc

### 12.1. Bối cảnh

Một Scrum Team làm nền tảng học trực tuyến gồm Product Owner, Scrum Master và Developers với các chuyên môn UI, backend, kiểm thử, dữ liệu. Team đặt **Product Goal**:

> “Người học có thể bắt đầu, lưu và tiếp tục bài học đáng tin, từng bước cải thiện tỷ lệ hoàn thành bài đầu.”

**Sprint Goal:** “Người học có thể lưu và mở lại tiến độ với phản hồi đúng khi lưu thành công hoặc thất bại.”

Nhóm có một số giả định ban đầu:

- Các PBI đã đủ nhỏ để kiểm thử trong Sprint.
- CI hoạt động đáng tin; ít phải chạy lại.
- UI và API có thể làm song song, tích hợp cuối Sprint không quá rủi ro.
- Một người chuyên trách review phần API là đủ.

Retrospective cần kiểm tra các giả định này thay vì quy kết bất cứ thành viên nào.

### 12.2. Bằng chứng Sprint A — dữ liệu giả định

**Toàn bộ dữ liệu trong case study là giả định để học.**

| Tín hiệu | Sprint A | Cần giải thích đúng |
|---|---:|---|
| PBI bắt đầu | 12 | Số bắt đầu, không phải giá trị giao |
| PBI đạt DoD | 7 | Chỉ những PBI thật sự hoàn thành |
| PBI chưa Done, đang chờ API hoặc review/test | 5 | Không đếm nhầm là Done |
| Integration tests thất bại được ghi nhận | 14 lượt | Phải phân loại lỗi code, test, môi trường |
| Sự cố test do dữ liệu dùng chung được xác minh | 8 lượt | Một nguyên nhân kỹ thuật có bằng chứng |
| Lỗi API contract phát hiện từ ngày 8 trở đi | 3 trường hợp | Có thể phát hiện sớm hơn không? |
| Người tham gia báo có làm thêm giờ cuối Sprint | 4 người | Cần xem thời lượng và tính lặp, không dùng để phán xét |
| PBI bị chặn có work item age trên 5 ngày | 3 PBI | Chờ ở đâu, vì sao? |
| Phản hồi Sprint Review | Thông điệp khi mất mạng chưa rõ | Cần Product Owner làm rõ ví dụ và ưu tiên |

Nhóm **không đưa tên cá nhân** cạnh những chỉ số này. Nếu có nhu cầu điều tra sự cố cụ thể, việc xác định thay đổi code và quyền sửa vẫn phải minh bạch theo quy trình kỹ thuật; nhưng dữ liệu retro không biến thành bảng điểm.

### 12.3. Lắng nghe góc nhìn trước khi diễn giải

Trong buổi retrospective:

- Developer frontend nói: “Khi API đổi trạng thái lỗi, tôi chỉ biết lúc tích hợp.”
- Developer backend nói: “Quy tắc timeout chưa được chốt từ đầu; tôi phải sửa hợp đồng nhiều lần.”
- Tester nói: “Tôi có thể kiểm tra sớm nếu có một endpoint và dữ liệu test riêng.”
- Product Owner nói: “Tôi đã trả lời về hành vi người dùng khi được hỏi, nhưng không biết lúc nào nhóm cần quyết định.”
- Scrum Master quan sát: “Nhiều PBI vẫn mở trong khi review và kiểm thử bị chờ; có thể có vấn đề WIP.”

Mỗi lời chia sẻ là **thông tin về trải nghiệm và rủi ro**, không được dùng như bằng chứng tự động rằng một người khác làm sai. Nhóm so khớp với timeline và trạng thái công việc.

### 12.4. Tái dựng chuỗi sự kiện

| Ngày | Điều xảy ra | Điều kiện nhóm xác định |
|---|---|---|
| 1 | Chọn PBI lưu tiến độ và UI phản hồi | Chưa có ví dụ timeout/chưa xác định |
| 3 | UI và backend triển khai theo các trạng thái tự hiểu | Không có contract test chạy cùng thay đổi |
| 5 | Kiểm thử tích hợp bắt đầu, pipeline đỏ khi chạy song song | Hai test dùng chung tài khoản và dữ liệu |
| 7 | Một số PBI mới vẫn được bắt đầu | WIP cao, các PBI cũ chưa đạt Done |
| 8–9 | Lỗi API và UI lộ ra, kiểm thử hồi quy dồn | Review phụ thuộc một người và môi trường khó tin |
| 10 | 7 PBI Done, 5 PBI chưa Done, thành viên làm thêm giờ | Cần điều chỉnh cách lập kế hoạch và chất lượng |

Sơ đồ dòng công việc minh họa:

~~~mermaid
flowchart LR
    A["PBI được bắt đầu"] --> B["Code UI / API riêng"]
    B --> C["Chờ contract / tích hợp"]
    C --> D["Chờ review / dữ liệu test"]
    D --> E{"Test và DoD đạt?"}
    E -->|"Chưa"| F["Sửa, chạy lại, chờ"]
    F --> C
    E -->|"Đạt"| G["Increment"]
~~~

**Điểm nghẽn không phải chỉ ở khâu Test.** Cách chia PBI, hợp đồng giao tiếp và chính sách dữ liệu thử làm hàng chờ tích tụ trước khi Tester có cơ hội xác minh.

### 12.5. Từ “đổ lỗi” sang giả thuyết có thể kiểm tra

Thay vì “QA kiểm thử chậm”, nhóm ghi:

> **Giả thuyết A:** vì các PBI được triển khai theo từng lớp UI/backend và tích hợp muộn, tester chỉ có luồng đầu–cuối để kiểm chứng ở cuối Sprint. Nếu chia lát dọc và tạo endpoint/test harness sớm hơn, công việc sẽ đạt DoD đều hơn.

Thay vì “CI không ổn định”, nhóm ghi:

> **Giả thuyết B:** dữ liệu thử dùng chung gây lỗi phụ thuộc thứ tự và chạy song song. Nếu mỗi test tự tạo/dọn dữ liệu riêng, tần suất thất bại không phản ánh lỗi code sẽ giảm.

Thay vì “Product Owner đổi yêu cầu”, nhóm ghi:

> **Giả thuyết C:** các trạng thái success/failure/unknown chưa được làm rõ trong refinement; UI và API đưa ra giả định khác nhau. Nếu dùng ví dụ chấp nhận và contract test trước khi tích hợp, lỗi hiểu sai sẽ được phát hiện sớm.

Những giả thuyết có thể **đồng thời đúng một phần**. Nhóm không cần chọn một người hay một phòng ban làm “nguyên nhân gốc duy nhất”.

### 12.6. Chọn một cặp thử nghiệm có tác động

Nhóm không cố thay đổi mọi thứ cùng lúc. Họ chọn hai thử nghiệm **minh họa**:

**Thử nghiệm 1 — Giảm phát hiện sai hợp đồng muộn**

- **Phạm vi:** các PBI thay đổi API lưu tiến độ trong Sprint B.
- **Hành động:** Three Amigos ngắn làm rõ trạng thái thành công, thất bại, chưa xác định; thêm kiểm tra hợp đồng UI–API trong CI.
- **Người phối hợp:** Product Owner làm rõ nghĩa nghiệp vụ; Developers có chuyên môn UI/API/test hiện thực.
- **Tín hiệu:** số sai hợp đồng sau ngày giữa Sprint, work item age tại khâu tích hợp, thời gian phản hồi CI.
- **Guardrail:** không hạ DoD, không tạo quá nhiều test trùng/giòn.

**Thử nghiệm 2 — Tạo dữ liệu integration test độc lập**

- **Phạm vi:** nhóm test có lịch sử lỗi do tài khoản dùng chung.
- **Hành động:** mỗi test tạo identifier/dữ liệu riêng, cleanup có kiểm soát, chờ theo trạng thái thay vì sleep cố định.
- **Người phối hợp:** Developers và người có chuyên môn kiểm thử/hạ tầng.
- **Tín hiệu:** tần suất thất bại không tái hiện, thời gian tìm nguyên nhân test đỏ.
- **Guardrail:** không tắt kiểm thử quan trọng hoặc dùng dữ liệu người dùng thật trái chính sách.

**WIP** được theo dõi như một **điều kiện hỗ trợ**: nhóm cố gắng hoàn tất các PBI đang mở, nhưng không tuyên bố có một con số WIP chuẩn chung nếu chưa đánh giá năng lực thực tế.

### 12.7. Kết quả Sprint B — minh họa, chưa chứng minh nhân quả

Giả sử sau thử nghiệm:

| Chỉ báo | Sprint A | Sprint B | Cách đọc thận trọng |
|---|---:|---:|---|
| PBI bắt đầu | 12 | 9 | Ít bắt đầu hơn chưa tự là tiến bộ |
| PBI đạt DoD | 7 | 8 | Có dấu hiệu hoàn tất tốt hơn, cần xem loại việc |
| PBI còn mở cuối Sprint | 5 | 1 | Sự dồn việc cuối Sprint có thể giảm |
| Lượt lỗi integration do dữ liệu chung | 8 | 1 | Tín hiệu phù hợp với thử nghiệm cô lập dữ liệu |
| Lỗi sai contract phát hiện sau giữa Sprint | 3 | 1 | Có thể phát hiện sớm hơn; cần thêm quan sát |
| Người báo làm thêm giờ cuối Sprint | 4 | 1 | Cần xem số giờ, bối cảnh và cảm nhận |
| Lỗi người dùng liên quan lưu tiến độ sau phát hành | Chưa đủ dữ liệu | Chưa đủ dữ liệu | **Không được kết luận cải thiện chất lượng production** |

Không thể khẳng định hai thay đổi **gây ra** toàn bộ chênh lệch giữa hai Sprint. Scope, độ khó PBI, người tham gia, mức phụ thuộc và sự cố bên ngoài có thể khác. Nhưng những chỉ số và lời kể có thể giúp nhóm quyết định **giữ thử nghiệm thêm một vài vòng và tiếp tục quan sát**.

### 12.8. Kết luận cải tiến

Tại Sprint Retrospective kế tiếp, nhóm trả lời:

1. **Điều đã thay đổi thật:** dữ liệu test riêng và contract tests được đưa vào CI; PBI lưu tiến độ được làm rõ sớm hơn.
2. **Điều quan sát được:** ít test đỏ do dữ liệu chung, nhiều PBI Done hơn trong mẫu nhỏ.
3. **Điều chưa biết:** chất lượng production và outcome người học có cải thiện lâu dài không?
4. **Điều tiếp theo:** giữ các thay đổi đang hữu ích, xem lại WIP/review và theo dõi lỗi thật qua vài Sprint.
5. **Điều cần truyền thông:** đã cải thiện vòng phản hồi kỹ thuật, nhưng chưa có đủ bằng chứng để nói Product Goal hoàn thành.

Đó là cải tiến dựa trên thực nghiệm: **không chỉ hành động, mà còn biết điều gì đã học và điều gì chưa thể kết luận**.

## 13. Điều chỉnh phương pháp nhìn lại theo bối cảnh đội

### 13.1. Đội phân tán và làm việc bất đồng bộ

Một retrospective phân tán có thể gặp:

- Thành viên ở các múi giờ khác nhau.
- Người ít nói khó chen vào cuộc gọi đông người.
- Thông tin ở nhiều công cụ và tin nhắn riêng.
- Kết nối mạng hoặc khả năng tiếp cận công cụ không đồng đều.

Thực hành có thể hỗ trợ:

1. Gửi mục tiêu và **dữ liệu không nhạy cảm** trước buổi họp.
2. Cho phép ghi nhận sự kiện, trải nghiệm và câu hỏi **bất đồng bộ**.
3. Dùng thời gian đồng bộ cho **giải thích khác biệt, phân tích và quyết định**, không đọc lần lượt bảng.
4. Luân phiên thời gian họp khi có nhiều múi giờ, tránh một nhóm luôn chịu bất lợi.
5. Chốt quyết định ở nơi tất cả người liên quan được phép xem.

Không mặc định ẩn danh trên công cụ online là bảo mật tuyệt đối; nhóm cần hiểu **quyền xem, lưu trữ và giới hạn ẩn danh**.

### 13.2. Đội mới hình thành hoặc có thành viên mới

Khi nhóm chưa quen phản hồi trực tiếp:

- Bắt đầu từ **sự kiện ít nhạy cảm**, điều tốt đã diễn ra và một vấn đề workflow cụ thể.
- Nhắc rõ hành vi tôn trọng, không cắt lời và quyền được không phát biểu về trải nghiệm cá nhân.
- Sử dụng viết im lặng để giảm ảnh hưởng người nói lớn.
- Tránh chấm điểm từng người hoặc so sánh tốc độ cá nhân.
- Chọn một cải tiến nhỏ có khả năng thành công và **thực hiện thật** để tạo niềm tin.

Không kỳ vọng một buổi retrospective biến một nhóm thiếu tin tưởng thành an toàn tuyệt đối. An toàn được tạo qua **những lần phản hồi được tiếp nhận công bằng và có hành động nhất quán**.

### 13.3. Có xung đột hoặc chênh lệch quyền lực

Nếu người quản lý tham gia với quyền đánh giá hiệu suất, các thành viên có thể ngại nêu vấn đề thật.

Người điều phối cần:

- Làm rõ mục đích và cách dùng thông tin.
- Cho phép kênh ghi nhận riêng khi cần.
- Không dùng quote có tên người làm bằng chứng kỷ luật ngoài mục đích đã thống nhất.
- Chuyển vấn đề quấy rối, phân biệt đối xử hoặc vi phạm nghiêm trọng sang quy trình phù hợp.
- Cân nhắc hỗ trợ của người điều phối trung lập khi mâu thuẫn quá căng.

**Blameless retrospective không phải miễn trách nhiệm**, nhưng cũng không phải cuộc họp để buộc người dễ tổn thương công khai trải nghiệm cho cả đội xem.

### 13.4. Đội bị chi phối bởi phụ thuộc bên ngoài

Nếu API của một nhóm khác thường đổi muộn, retrospective chỉ nói “nhóm kia nên hợp tác tốt hơn” sẽ không tạo thay đổi.

Những việc đội có thể làm:

- Ghi thời điểm nhận hợp đồng, thời gian chờ và tác động tới PBI.
- Chia PBI để hạn chế phụ thuộc khi khả thi.
- Đề xuất **contract tests, versioning và lịch trao đổi** với đối tác.
- Nhờ Scrum Master hỗ trợ gỡ trở ngại vượt phạm vi đội.
- Điều chỉnh ưu tiên/nhịp tích hợp khi thông tin từ bên ngoài chưa chắc.

Đội không thể tự quyết thay thẩm quyền của nhóm khác, nhưng có thể đưa **bằng chứng và đề xuất cụ thể** để tổ chức giải quyết vấn đề.

### 13.5. Retro sau một sự cố production

Khi xảy ra mất dữ liệu, lộ quyền truy cập hoặc ngừng dịch vụ:

1. Ưu tiên **bảo vệ người dùng và khôi phục** theo quy trình ứng cứu.
2. Hậu kiểm sự cố có thể dựng timeline kỹ thuật, tác động, tín hiệu phát hiện và những điều kiện cho phép lỗi lan.
3. Retrospective xem **cách Scrum Team phối hợp và hệ thống chất lượng** có thể được cải thiện.
4. Thông tin nhạy cảm, dữ liệu riêng tư và trách nhiệm pháp lý phải được xử lý trong kênh có thẩm quyền.
5. Không ép đội làm “trò chơi vui vẻ” khi còn phải đối phó thiệt hại nghiêm trọng; chọn format và nhịp phù hợp.

Mục tiêu là cải tiến lâu dài, **không lặp lại một cuộc điều tra để tìm người chịu tội**.

### 13.6. Khi không có đủ dữ liệu định lượng

Nhóm nhỏ hoặc mới có thể chưa có dashboard đáng tin. Vẫn có thể retro dựa trên:

- Một vài PBI có timeline rõ.
- Quan sát trạng thái công việc và blocker.
- Kết quả CI/review được ghi lại.
- Ví dụ phàn nàn hoặc phản hồi của người dùng có nguồn gốc.
- Trải nghiệm của các thành viên, có nêu giới hạn.

Sau đó chọn **một cải tiến trong cách thu dữ liệu** để Sprint sau hiểu rõ hơn. Đừng tự tạo dữ liệu hoặc biến “chúng tôi cảm thấy nhanh” thành một tỷ lệ chính xác.

## 14. Kết hợp Scrum, Kanban, Lean và XP trong cải tiến liên tục

### 14.1. Scrum: inspect and adapt cả sản phẩm lẫn cách làm

Scrum có Sprint Review để kiểm tra Increment/bối cảnh sản phẩm và Sprint Retrospective để cải thiện **chất lượng, hiệu quả cách Scrum Team làm việc**.

Ví dụ:

| Tín hiệu | Điểm kiểm tra phù hợp | Hành động |
|---|---|---|
| Người học không hiểu trạng thái lưu khi mất mạng | Sprint Review/feedback sản phẩm | Product Owner sắp lại Product Backlog, làm rõ acceptance criteria |
| Sai hợp đồng UI–API phát hiện muộn mỗi Sprint | Sprint Retrospective | Thử contract tests sớm, chia lát cắt dọc |
| Sprint Goal bị đe dọa vì dependency ngay hôm nay | Daily Scrum và trao đổi cần thiết | Developers điều chỉnh Sprint Backlog/kế hoạch |
| DoD chưa đạt vì test tích hợp đỏ | Trong Sprint, không chờ retro | Không báo Done; giải quyết rủi ro, minh bạch trạng thái |

**Retrospective không phải nơi hợp thức hóa việc giao Increment chưa đạt DoD.** Nó giúp cải thiện cơ chế để ít xảy ra tình trạng đó hơn.

### 14.2. Kanban: nhìn dòng công việc thay vì nhìn số người bận

Kanban có thể giúp quan sát:

- **WIP** quá cao làm việc dở tích tụ.
- **Work item age** cho biết hạng mục nào đã mở quá lâu cần chú ý.
- **Cycle time** và phân bố của việc Done để xem khả năng giao.
- **Throughput** để theo dõi số hạng mục hoàn tất trong khoảng.
- **Chính sách kéo việc/pull** để ưu tiên hoàn thành trước khi mở thêm.

Một retrospective có thể hỏi: “Điều kiện nào khiến work item age tăng trong khi mọi người đều rất bận?” Đây là câu hỏi **về dòng công việc**, không phải yêu cầu mọi người làm nhanh hơn riêng lẻ.

Kanban không bắt buộc phải có tên sự kiện “Sprint Retrospective”, nhưng các vòng đánh giá dịch vụ, flow và cải tiến chính sách giúp **inspect/adapt** trong workflow được áp dụng.

### 14.3. XP: thay đổi kỹ thuật giúp học nhanh hơn

**Extreme Programming** có các thực hành kỹ thuật có thể trở thành hành động cải tiến:

- **TDD:** phát hiện lỗi quy tắc nhỏ khi code còn mới.
- **Pair programming:** tạo review sớm, chia tri thức và giảm phụ thuộc cá nhân.
- **Refactoring:** cải thiện cấu trúc để thay đổi an toàn.
- **Continuous Integration:** phát hiện xung đột sớm khi tích hợp thường xuyên.
- **Small releases:** nhận phản hồi sản phẩm sớm hơn với lát cắt đủ chất lượng.
- **Sustainable pace:** giảm vòng lặp kiệt sức–bỏ test–lỗi–làm lại.

Không nên biến một retrospective thành quyết định “từ ngày mai dùng tất cả thực hành XP 100%”. Chọn **một vấn đề và vài cơ chế hỗ trợ nhau**, kiểm chứng tác dụng.

### 14.4. Lean: cải tiến tại nguồn và giảm lãng phí

Lean nhấn mạnh giá trị, nhìn dòng công việc, giảm lãng phí và cải tiến liên tục (**Kaizen**).

Đối với một lỗi bị phát hiện cuối Sprint:

- Hỏi **điểm sớm nhất hợp lý** có thể phát hiện hoặc phòng ngừa.
- Giảm **lô công việc lớn** và việc đang làm dở.
- Hiển thị điều bất thường và giải quyết nguyên nhân, không đẩy tiếp lỗi sang bước sau.
- Thử một thay đổi nhỏ, đo kết quả và điều chỉnh.

**Không đồng nghĩa** giảm mọi bước kiểm tra vì chúng tiêu tốn thời gian. Kiểm soát bảo mật, dữ liệu và chất lượng thiết yếu **tạo giá trị bằng việc phòng rủi ro**, không phải lãng phí đơn thuần.

### 14.5. Cùng một cải tiến, nhiều góc nhìn bổ trợ

**Vấn đề:** API và UI thường không khớp trạng thái lỗi tới cuối Sprint.

| Góc nhìn | Cách nhìn vấn đề |
|---|---|
| **Scrum** | Điều này ảnh hưởng Sprint Goal, Increment và DoD thế nào? |
| **Kanban** | Work item age và hàng chờ tích hợp đang tăng ở đâu? |
| **XP** | Có thể dùng TDD, contract tests, pairing và CI để phản hồi sớm hơn không? |
| **Lean** | Vì sao lỗi lan tới khâu cuối, việc làm lại có thể giảm từ nguồn nào? |
| **Sản phẩm** | Điều kiện chấp nhận và trạng thái người học cần có được làm rõ không? |

Chúng không phải những nhãn phải áp dụng đủ, mà là **các góc nhìn hữu ích để tìm nguyên nhân và chọn can thiệp**.

## 15. Một số kỹ thuật điều phối phù hợp với mục tiêu nhìn lại

### 15.1. Start – Stop – Continue

Đặt ba câu hỏi:

- **Start:** điều gì nên bắt đầu thử để cải thiện?
- **Stop:** điều gì đang tạo lãng phí/rủi ro mà có thể ngừng hoặc giảm?
- **Continue:** điều gì đã giúp tạo giá trị và nên duy trì?

Ví dụ:

| Start | Stop | Continue |
|---|---|---|
| Làm rõ ví dụ timeout trước khi code API | Đợi đến cuối Sprint mới kiểm thử tích hợp | Pairing khi sửa module rủi ro |
| Cô lập dữ liệu integration test | Mở thêm nhiều PBI khi review đã tắc | Cho CI phản hồi thường xuyên |

**Rủi ro:** format này dễ tạo danh sách ý kiến mà không biết bằng chứng. Nên yêu cầu **mỗi thẻ có một ví dụ/sự kiện cụ thể** và kết thúc bằng một thử nghiệm được chọn.

### 15.2. 4Ls: Liked, Learned, Lacked, Longed for

Các câu hỏi:

- **Liked:** điều đã diễn ra tốt và có giá trị.
- **Learned:** điều mới học được.
- **Lacked:** nguồn lực, thông tin hoặc hỗ trợ còn thiếu.
- **Longed for:** điều đội muốn có trong tương lai.

Ví dụ **Lacked**: “Không có tài khoản test riêng để chạy song song”. Nó giúp chuyển từ câu “CI không tốt” sang **điều kiện làm việc cụ thể**.

**Rủi ro:** “Longed for” có thể thành danh sách mong muốn lớn. Hãy tìm **bước tiếp theo nhỏ và khả thi** thay vì cam kết xây mọi công cụ mong muốn.

### 15.3. Timeline + sự kiện–cảm nhận

Với Sprint có sự cố hoặc nhiều phụ thuộc, đặt trục thời gian và hai hàng:

1. **Sự kiện có thể kiểm chứng:** API thay, CI đỏ, PBI bị chặn, release, feedback.
2. **Trải nghiệm:** bất định, vui mừng, lo lắng, áp lực hoặc tin tưởng ở thời điểm đó.

Ví dụ một thành viên cảm thấy nhẹ nhõm khi contract test lần đầu phát hiện lỗi trước merge. Nhóm có thể hỏi **điều kiện nào tạo phản hồi tích cực này**, rồi duy trì nó.

Đừng yêu cầu ai đó công khai cảm xúc hoặc tình trạng cá nhân mà họ không muốn chia sẻ.

### 15.4. “Mad, Sad, Glad” hoặc nhiệt kế cảm nhận

Format giúp người tham gia kể lại cảm nhận, có ích khi tải công việc và an toàn tâm lý là vấn đề. Tuy nhiên:

- Không coi một cảm nhận là dữ liệu định lượng chính xác.
- Không dùng để ép người tham gia bộc lộ trải nghiệm nhạy cảm.
- Nên ghép với sự kiện và điều kiện, rồi hỏi “thay đổi nào có thể hỗ trợ?”.

### 15.5. Lean Coffee cho nhiều chủ đề

Khi có nhiều vấn đề, nhóm có thể đề xuất thẻ chủ đề, cùng ưu tiên thứ tự trao đổi, đặt timebox ngắn và quyết định tiếp tục hay chuyển chủ đề.

**Rủi ro:** chủ đề được nhiều người bình chọn không nhất thiết là rủi ro lớn nhất. Một sự cố an toàn nghiêm trọng không nên bị loại chỉ vì ít người muốn bàn công khai; cần kênh xử lý phù hợp.

### 15.6. Khi nào chọn kỹ thuật nào?

| Bối cảnh | Kỹ thuật hữu ích | Điều cần bảo vệ |
|---|---|---|
| Sprint bình thường, cần cải tiến nhanh | Start–Stop–Continue | Có bằng chứng và hành động cụ thể |
| Đội muốn duy trì điều tốt đồng thời nói điều thiếu | 4Ls | Không để mong muốn trở thành backlog vô hạn |
| Có sự cố, nhiều diễn biến và cách nhớ khác nhau | Timeline | Không biến timeline thành truy lỗi cá nhân |
| Đội quá tải hoặc ít người dám nói | Viết im lặng, 4Ls, thảo luận cảm nhận an toàn | Kênh riêng cho vấn đề nhạy cảm |
| Nhiều chủ đề, nhóm cần chủ động chọn | Lean Coffee hoặc phân nhóm thẻ | Không bỏ qua rủi ro nghiêm trọng |
| Cần hiểu điểm nghẽn lặp nhiều Sprint | Kanban metrics + timeline + causal analysis | Dữ liệu có định nghĩa và không dùng xếp hạng |

Không nên đổi format mỗi Sprint chỉ để tránh nhàm chán. **Chọn format phù hợp câu hỏi và điều kiện nhóm**, rồi chú trọng hành động sau buổi họp.

## 16. Những ngộ nhận và phản mẫu cần tránh

| Ngộ nhận / phản mẫu | Vì sao có hại? | Cách điều chỉnh |
|---|---|---|
| “Retrospective là buổi phân tích ai làm sai.” | Tạo phòng thủ, giấu lỗi, bỏ qua điều kiện hệ thống | Xem sự kiện, tương tác, quy trình, công cụ và DoD |
| “Dữ liệu đã đủ, không cần nghe người trong nhóm.” | Dashboard có thể không cho thấy chuyển ngữ cảnh, áp lực, bất định | Kết hợp định lượng và trải nghiệm |
| “Ai cảm thấy thế nào thì đó là sự thật khách quan.” | Nhầm cảm nhận với sự kiện | Tôn trọng cảm nhận, đối chiếu điều kiện và bằng chứng |
| “An toàn tâm lý nghĩa là không được bất đồng.” | Tránh vấn đề khó và thiếu học hỏi | Cho phép bất đồng tôn trọng, có căn cứ |
| “Bỏ tên người là đủ để ẩn danh.” | Bối cảnh nhỏ có thể vẫn nhận ra người | Cân nhắc quyền riêng tư, quyền xem và kênh phù hợp |
| “Điều gì xảy ra cũng hỏi đến Why thứ năm.” | Tạo nguyên nhân giả hoặc đổ lỗi trá hình | Dùng 5 Whys như công cụ, kiểm chứng bằng dữ liệu |
| “Root cause lúc nào cũng là một người.” | Bỏ qua tương tác nhiều điều kiện | Xem cơ chế, kiểm soát và khả năng phát hiện |
| “Sprint nào cũng phải có ít nhất 10 hành động.” | Tăng WIP, không đủ năng lực thực hiện | Chọn 1–2 thử nghiệm đáng làm, đo được |
| “Nêu hành động là đã cải tiến.” | Không ai làm, không có kiểm chứng | Gắn chủ sở hữu, phạm vi, mốc xem lại và tín hiệu |
| “Đã triển khai action thì action thành công.” | Output không chứng minh kết quả | Xem guardrails, flow, chất lượng và phản hồi |
| “Velocity giảm là đội làm kém.” | Story points không so được và dễ bị gaming | Xem Sprint Goal, DoD, flow và bối cảnh |
| “Cứ tăng throughput thì chất lượng tốt.” | Có thể chia ticket nhỏ hoặc báo Done sớm | Kết hợp chất lượng, outcome và định nghĩa work item |
| “CI xanh là mọi rủi ro đã biến mất.” | Test có thể thiếu hoặc chạy trên môi trường không đại diện | Xem độ tin cậy, coverage theo rủi ro và production |
| “CI đỏ lặp thì tạm bỏ test để kịp Sprint.” | Giảm khả năng phát hiện lỗi và mất niềm tin | Điều tra, ổn định test; chỉ quản lý ngoại lệ có kiểm soát |
| “Nếu nhóm không tự sửa được thì đừng ghi trở ngại.” | Vấn đề tổ chức bị giấu | Nêu bằng chứng, người có thẩm quyền và lộ trình hỗ trợ |
| “Scrum Master phải giải quyết tất cả thay nhóm.” | Làm yếu quyền tự quản và trách nhiệm chung | Scrum Master hỗ trợ gỡ trở ngại; Developers/PO làm phần trong trách nhiệm |
| “Product Owner có thể yêu cầu bỏ DoD để kịp deadline.” | Hủy ý nghĩa Increment và đẩy rủi ro tới người dùng | Giữ chất lượng, thương lượng phạm vi phù hợp |
| “Retrospective là nơi duy nhất được nêu blocker.” | Phản hồi quá muộn | Xử lý liên tục; retro nhìn mẫu hình và cải tiến |
| “Không có số liệu lớn thì không được cải tiến.” | Bỏ lỡ thử nghiệm nhỏ ít rủi ro | Ghi giới hạn bằng chứng, đo phù hợp rồi học |
| “Nhóm tiến bộ vì Sprint B tốt hơn Sprint A.” | Có thể scope, số mẫu và yếu tố ngoài khác | Dùng dữ liệu trước–sau thận trọng và thử tiếp |
| “Sự cố nghiêm trọng cứ đưa ra retro toàn đội.” | Có thể lộ thông tin nhạy cảm hoặc làm người bị hại chịu áp lực | Ứng cứu, hậu kiểm và kênh phù hợp theo quyền hạn |
| “Retrospective phải vui, không được nói vấn đề khó.” | Che mâu thuẫn và điểm đau thật | Tạo môi trường tôn trọng, nói thật và hành động |
| “Đã chọn action thì không được thay đổi.” | Ép đội tiếp tục một thử nghiệm không hiệu quả | Giữ–điều chỉnh–dừng theo bằng chứng |

## 17. Checklist tổ chức retrospective dựa trên sự kiện

### 17.1. Trước buổi nhìn lại

1. **Mục đích:** điều gì cần học để tăng chất lượng hoặc hiệu quả?
2. **Sprint Goal:** mục tiêu Sprint và trạng thái thực tế đã rõ chưa?
3. **DoD:** có phân biệt việc Done với việc chỉ xong code không?
4. **Sự kiện:** có timeline hoặc bằng chứng đủ để thảo luận không?
5. **Flow:** WIP, work item age, cycle time, throughput có được diễn giải đúng?
6. **Chất lượng:** lỗi hồi quy, CI, phản hồi người dùng nào liên quan?
7. **Điều kiện:** phụ thuộc, năng lực, WIP, công cụ, nhịp làm và quyền quyết định?
8. **An toàn:** người tham gia có thể nói mà không bị đánh giá hiệu suất không?
9. **Quyền riêng tư:** dữ liệu và chi tiết nhạy cảm có được bảo vệ?
10. **Hành động cũ:** nhóm đã kiểm tra kết quả thử nghiệm retro trước chưa?

### 17.2. Trong buổi nhìn lại

11. **Phân biệt:** sự kiện, số liệu, cảm nhận và giả thuyết?
12. **Đủ tiếng nói:** người ít nói hoặc làm việc từ xa có cơ hội tham gia?
13. **Không quy kết:** câu hỏi hướng vào cơ chế, không nhãn con người?
14. **Nhiều phía:** có xem cả điều giúp thành công và điều gây cản trở?
15. **Nguyên nhân:** có đánh dấu điều đã xác minh và điều cần kiểm tra tiếp?
16. **Quyền thay đổi:** điều nào đội tự làm được, điều nào cần tổ chức hỗ trợ?
17. **Ưu tiên:** nhóm có chọn ít việc thay vì tạo danh sách vô hạn?
18. **Giả thuyết cải tiến:** thay đổi nào được kỳ vọng tạo tác dụng gì?
19. **Chất lượng:** có giữ DoD và kiểm soát rủi ro bắt buộc?

### 17.3. Sau buổi nhìn lại

20. **Hành động:** có người phối hợp, phạm vi, nơi theo dõi rõ?
21. **Năng lực:** đã bố trí thời gian cho hành động cải tiến, không đẩy thành việc ngoài giờ?
22. **Tín hiệu:** có tiêu chí xem lại về flow/chất lượng/điều kiện làm việc?
23. **Guardrails:** có gì không được xấu đi khi thử?
24. **Mốc xem lại:** trong hoặc sau Sprint nào sẽ đánh giá?
25. **Thông tin:** những người liên quan có biết quyết định và đánh đổi?
26. **Thích ứng:** nếu kết quả trái dự đoán, có sẵn sàng sửa/dừng thử nghiệm?

Checklist là **công cụ tự rà soát**, không phải thủ tục phải đọc tuần tự từng mục trong mọi retrospective. Chọn mức chi tiết tương xứng rủi ro và tình trạng nhóm.

## 18. Bài tập vận dụng

### Bài tập 1 — Phân loại sự kiện, cảm nhận và giả thuyết

Đọc những phát biểu sau:

1. “Tại cuối Sprint, 5 trong 12 PBI chưa đạt Definition of Done.”
2. “Tôi cảm thấy review luôn đến quá muộn.”
3. “Ba test cùng ghi một tài khoản thử, có thể gây xung đột.”
4. “Ngày 6 pipeline đỏ khi chạy song song, nhưng chạy riêng thì qua.”
5. “Nếu giới hạn WIP ở bước phát triển, hàng chờ kiểm thử có thể giảm.”
6. “Chúng ta nên chuyển tài khoản thử sang cơ chế dữ liệu riêng.”

**Yêu cầu:** phân loại **sự kiện/dữ liệu, cảm nhận, giả thuyết nguyên nhân, giả thuyết cải tiến và quyết định**. Với những phát biểu chưa kiểm chứng, nêu bằng chứng cần thu thêm.

**Gợi ý:** (1) dữ liệu trạng thái nếu DoD được dùng nhất quán; (2) cảm nhận; (3) giả thuyết nguyên nhân cần xác nhận; (4) sự kiện kiểm thử; (5) giả thuyết cải tiến; (6) đề xuất hành động.

### Bài tập 2 — Thiết kế agenda 75 phút

Nhóm tám người có Sprint hai tuần. Một số thành viên làm việc từ xa; hai người mới thường ít nói. Vấn đề chính là PBI chờ review cuối Sprint và một số test flaky.

**Yêu cầu:**

- Chia 75 phút thành các phần **mở đầu, thu thập dữ liệu, tìm hiểu, chọn hành động, kết thúc**.
- Nêu cách thu ý kiến người ít nói mà không ép chia sẻ cảm xúc cá nhân.
- Xác định ba dữ liệu chuẩn bị trước.
- Viết hai quy tắc trao đổi giúp bảo vệ an toàn tâm lý.
- Chọn một đầu ra tối thiểu phải có sau cuộc họp.

### Bài tập 3 — Dựng timeline

Một Sprint có các mốc:

- Ngày 2: API bắt đầu đổi kiểu trạng thái lỗi.
- Ngày 4: UI hoàn thành code theo hợp đồng cũ.
- Ngày 6: integration test bắt đầu chạy và thất bại.
- Ngày 8: nhóm nhận ra UI và API hiểu khác nhau.
- Ngày 9: Test bổ sung ví dụ mất mạng, phát hiện thông báo sai.
- Ngày 10: nhiều PBI còn chờ kiểm thử và review.

**Yêu cầu:**

1. Dựng timeline hai cột **sự kiện** và **điều kiện làm việc**.
2. Nêu ít nhất ba câu hỏi **“vì sao?”** không mang tính quy kết.
3. Chỉ ra điểm nào có thể nhận phản hồi sớm hơn.
4. Đề xuất một cải tiến có giả thuyết kiểm chứng.
5. Nêu một điều chưa biết cần tiếp tục điều tra.

### Bài tập 4 — Dùng 5 Whys mà không đổ lỗi

Lỗi: integration tests thường thất bại ngẫu nhiên trên CI nhưng chạy riêng trên máy Developer thì qua.

**Yêu cầu:**

- Viết tối đa năm câu hỏi Why để tìm điều kiện về dữ liệu thử, đồng thời và môi trường.
- Đánh dấu câu trả lời **đã xác minh** hoặc **giả thuyết**.
- Không dùng “vì người X thiếu cẩn thận” làm nguyên nhân cuối cùng.
- Đề xuất một cải tiến kỹ thuật có người phối hợp và cách đo độ tin cậy.
- Nêu rủi ro nếu chỉ “rerun đến khi xanh”.

### Bài tập 5 — Chọn ít hành động có tác động

Trong một buổi retro, nhóm đưa ra bảy ý:

1. Dùng dữ liệu riêng cho integration tests.
2. Tăng số cuộc họp cập nhật.
3. Thêm contract tests cho API quan trọng.
4. Viết lại toàn bộ frontend.
5. Pair khi sửa module chỉ một người hiểu.
6. Bắt mọi Developer có thêm ít nhất 20 unit tests/ngày.
7. Thử giới hạn WIP để ưu tiên hoàn tất.

**Yêu cầu:** chọn **tối đa hai hành động** cho Sprint tiếp theo. Giải thích chúng liên quan sự kiện và rủi ro nào, vì sao không chọn các phương án còn lại lúc này, và đặt hai tín hiệu/guardrail.

**Gợi ý:** tránh tăng họp và định mức số test như mục tiêu tự thân; không cần viết lại hệ thống nếu chưa có bằng chứng.

### Bài tập 6 — Đọc số liệu Sprint A và B

| Tín hiệu | Sprint A | Sprint B |
|---|---:|---:|
| PBI bắt đầu | 12 | 9 |
| PBI đạt DoD | 7 | 8 |
| PBI còn mở cuối Sprint | 5 | 1 |
| Lượt lỗi integration liên quan dữ liệu dùng chung | 8 | 1 |
| Lỗi người dùng sau phát hành | Chưa đo đủ | Chưa đo đủ |

**Yêu cầu:**

1. Nêu hai tín hiệu có thể ủng hộ việc thử nghiệm cải tiến hữu ích.
2. Giải thích vì sao không được kết luận năng suất tăng cố định từ hai Sprint.
3. Chỉ ra một chỉ số chưa có nên bổ sung.
4. Nêu một câu hỏi về cách định nghĩa PBI hoặc độ phức tạp trước–sau.
5. Đề xuất điều kiện giữ hoặc điều chỉnh thử nghiệm trong Sprint C.

### Bài tập 7 — Retrospective trong nhóm phân tán

Nhóm có thành viên ở Việt Nam, châu Âu và Mỹ. Buổi retrospective trực tuyến thường do nhóm đông người nói chính; các thành viên khác ít tham gia, một số không thể dự do múi giờ.

**Yêu cầu:** thiết kế cách thu thập dữ liệu bất đồng bộ và thảo luận đồng bộ công bằng hơn. Nêu:

~~~text
Mục tiêu retro:
Cách chia sẻ dữ liệu trước buổi:
Kênh thu ý kiến và quyền riêng tư:
Cách để người ít nói tham gia:
Cách chọn thời điểm họp:
Cách ghi nhận ý kiến không dự họp:
Quyết định / người phối hợp:
Điều cần đo sau một vài vòng:
~~~

### Bài tập 8 — Vấn đề vượt quyền của nhóm

Một nhóm không thể chạy integration tests vì tổ chức chỉ có một môi trường dùng chung, quyền tạo database thử do bộ phận khác nắm giữ. Scrum Team đã ghi vấn đề trong ba retrospective.

**Yêu cầu:**

1. Xác định vì sao đây là trở ngại hệ thống, không thể chỉ yêu cầu Developers “cố hơn”.
2. Đề xuất dữ liệu chứng minh tác động: thời gian chờ, test failures, work item age...
3. Nêu trách nhiệm hỗ trợ của Scrum Master và cách phối hợp với bên có thẩm quyền.
4. Đưa ra một biện pháp giảm tác động tạm thời **không vi phạm chính sách quyền truy cập**.
5. Định nghĩa mốc xem lại để tránh ghi lặp vấn đề mà không chuyển biến.

### Bài tập 9 — Viết thẻ thử nghiệm cải tiến

Nhóm nhận thấy PBI thường chờ tới cuối Sprint mới được kiểm thử, khiến nhiều lỗi hồi quy được phát hiện quá muộn.

Điền mẫu:

~~~text
Product Goal / Sprint Goal liên quan:
Vấn đề cụ thể:
Sự kiện và dữ liệu nền:
Điều kiện làm việc liên quan:
Giả thuyết nguyên nhân:
Giả thuyết cải tiến:
Hành động cụ thể trong Sprint tới:
Phạm vi thử:
Người phối hợp / hỗ trợ:
Tín hiệu về flow:
Tín hiệu về chất lượng:
Guardrails / điều không được đánh đổi:
Điểm xem lại:
Điều kiện giữ, sửa hoặc dừng:
~~~

**Gợi ý:** một thẻ tốt có thể kiểm chứng tác dụng; không chỉ ghi “Cả nhóm nỗ lực kiểm thử sớm hơn”.

### Bài tập 10 — Hậu kiểm sự cố và Sprint Retrospective

Sau phát hành, một lỗi làm người học mất tiến độ và nhóm phải ứng cứu trong đêm. Một quản lý muốn mời toàn bộ công ty vào Sprint Retrospective để tìm “người viết lỗi”.

**Yêu cầu:**

1. Phân biệt việc cần làm **ngay trong ứng cứu** với việc cần làm ở **hậu kiểm sự cố** và **Sprint Retrospective**.
2. Giải thích vì sao không nên biến retro thành buổi truy trách nhiệm cá nhân.
3. Nêu cách bảo vệ dữ liệu người học và chi tiết nhạy cảm khi thảo luận.
4. Đề xuất một kiểm soát tại nguồn và một cải tiến phản hồi vận hành.
5. Nêu cách đánh giá thay đổi sau vài Sprint.

### Bài tập 11 — Cân bằng chỉ số và cảm nhận

Nhóm báo throughput tăng, nhưng nhiều thành viên nói họ kiệt sức, phải làm thêm giờ và thường bỏ qua review kỹ lưỡng.

**Yêu cầu:** giải thích vì sao throughput tăng **chưa chứng minh hệ thống làm việc tốt hơn**. Đề xuất thêm hai tín hiệu chất lượng, hai tín hiệu bền vững và cách thảo luận an toàn với nhóm. Nêu phương án thay đổi WIP hoặc lập kế hoạch mà không hạ DoD.

### Bài tập 12 — Tạo buổi nhìn lại cho dự án của bạn

Chọn một Sprint hoặc giai đoạn làm việc thật có dữ liệu được phép dùng. Hoàn thành bản thiết kế ngắn:

~~~text
Mục tiêu nhìn lại:
Người tham gia và quy tắc an toàn:
Sự kiện quan trọng:
Tín hiệu về flow / chất lượng / sản phẩm:
Trải nghiệm nhóm cần lắng nghe:
Điều kiện làm việc nổi bật:
Điều đã xác minh / điều còn chưa biết:
1–2 giả thuyết nguyên nhân:
Hành động cải tiến trong quyền nhóm:
Trở ngại cần tổ chức / PO / Scrum Master hỗ trợ:
Phạm vi, người phối hợp, tín hiệu và guardrail:
Mốc đánh giá lại:
Điều cần nói với stakeholder:
~~~

**Tự đánh giá:** bản thiết kế có cho thấy người tham gia **hiểu hệ thống làm việc tốt hơn và có một thử nghiệm khả thi**, hay chỉ liệt kê lời phàn nàn và khẩu hiệu?

## 19. Tổng kết

Tổ chức nhìn lại dựa trên sự kiện và điều kiện làm việc là cách biến **Sprint Retrospective và các vòng cải tiến Agile** thành hoạt động học hỏi có tác động:

1. **Bắt đầu từ điều đã diễn ra:** timeline, trạng thái Done, dữ liệu flow/chất lượng và trải nghiệm của người tham gia.
2. **Phân biệt sự kiện với cảm nhận và giả thuyết:** tôn trọng trải nghiệm nhưng không suy luận nguyên nhân thiếu bằng chứng.
3. **Nhìn điều kiện hệ thống:** WIP, kích thước PBI, độ rõ yêu cầu, CI, môi trường, phụ thuộc, quyền quyết định và nhịp làm việc.
4. **Bảo đảm an toàn tâm lý:** hỏi về cơ chế, không dán nhãn con người; dùng kênh phù hợp cho vấn đề nhạy cảm.
5. **Dùng retrospective đúng mục đích:** cải thiện chất lượng và hiệu quả; Sprint Review kiểm tra Increment/bối cảnh sản phẩm, Daily Scrum điều chỉnh kế hoạch hướng Sprint Goal.
6. **Phân tích nguyên nhân có kiểm chứng:** 5 Whys, timeline hoặc causal map chỉ hỗ trợ đặt câu hỏi, không phải bằng chứng tự thân.
7. **Chọn ít thử nghiệm có thể làm:** mô tả hành động, người phối hợp, phạm vi, tín hiệu, guardrail và mốc xem lại; phân bổ năng lực thật.
8. **Đo kết quả và bảo vệ chất lượng:** WIP, work item age, cycle time, throughput, CI, lỗi production và outcome người dùng phải được nhìn cùng nhau; không hạ Definition of Done.
9. **Kết hợp Scrum, Kanban, XP và Lean theo nhu cầu:** cải tiến tổ chức, dòng công việc và kỹ thuật hỗ trợ nhau để phản hồi sớm, giao Increment đáng tin và làm việc bền vững.
10. **Khép vòng học:** sau khi thử, xem điều gì thay đổi, điều gì chưa rõ, rồi **giữ, sửa hoặc dừng** cách làm thay vì lặp lại cùng một lời hứa mỗi Sprint.

> **Câu hỏi ghi nhớ:** “Nếu một khó khăn lặp lại trong nhiều Sprint, **sự kiện và điều kiện nào đang cho phép nó xuất hiện**, và thử nghiệm nhỏ nào có thể tạo **bằng chứng mới** rằng cách làm của chúng ta đang cải thiện?”

### Tài liệu tham khảo

- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Sprint Retrospective, Sprint Review, Sprint Goal, Increment, Definition of Done và empiricism.
- [Manifesto for Agile Software Development](https://agilemanifesto.org/) và [12 Principles](https://agilemanifesto.org/principles.html) — sự xuất sắc kỹ thuật, nhịp làm việc bền vững và thường xuyên nhìn lại để cải tiến.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, work item age, throughput và cycle time trong quản lý dòng công việc.
- Esther Derby và Diana Larsen, *Agile Retrospectives: Making Good Teams Great* — khung điều phối Set the Stage, Gather Data, Generate Insights, Decide What to Do và Close.
- [Agile Alliance — Retrospective](https://agilealliance.org/glossary/retrospective/) — mục đích và các thực hành phổ biến của retrospective trong Agile.
- [Google SRE — Postmortem Culture](https://sre.google/sre-book/postmortem-culture/) — học từ sự cố, hậu kiểm không đổ lỗi và cải tiến cơ chế phòng ngừa.
- [Agile Alliance — Extreme Programming](https://agilealliance.org/glossary/xp/) — TDD, pair programming, refactoring, continuous integration và phát hành nhỏ.
- [Lean Enterprise Institute](https://www.lean.org/) — Kaizen, nhìn hệ thống tạo giá trị, giảm lãng phí và cải tiến liên tục.
