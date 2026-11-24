# Minh bạch thông tin để nhóm và bên liên quan cùng hiểu thực tế

## Mục tiêu học tập

Sau bài học, bạn có thể:

1. Giải thích **minh bạch (transparency)** là nền tảng của tư duy thực nghiệm trong Agile, liên hệ với **kiểm tra (inspection)** và **thích nghi (adaptation)**.
2. Xác định thông tin nào cần được chia sẻ để nhóm phát triển, người phụ trách sản phẩm và các bên liên quan có cùng hiểu biết về mục tiêu, tiến độ, chất lượng và rủi ro.
3. Thiết kế cách hiển thị thông tin bằng Product Backlog, Sprint Backlog, Increment, Definition of Done, bảng Kanban và những tín hiệu đo lường có ngữ cảnh.
4. Phân biệt dữ kiện đã quan sát, giả định, dự báo và cam kết; trình bày bất định trung thực thay vì tạo cảm giác chính xác giả.
5. Thực hành giao tiếp về một vấn đề khó, giúp người nghe cùng ra quyết định dựa trên bằng chứng mà vẫn bảo vệ thông tin cần giữ kín.

## 1. Vì sao minh bạch là nền tảng của tư duy thực nghiệm?

Agile phát triển phần mềm theo cách học hỏi từ những gì thực sự xảy ra: giao sản phẩm tăng dần, nhận phản hồi sớm và cải tiến liên tục. Khi nhiều yếu tố chưa chắc chắn — nhu cầu người dùng, giải pháp kỹ thuật, năng lực đội, phụ thuộc — một kế hoạch dựa trên giả định ban đầu không đủ để chỉ đạo toàn bộ dự án.

**Tư duy thực nghiệm (empiricism)** có nghĩa là ra quyết định dựa trên điều đã quan sát được và kiến thức tích lũy qua trải nghiệm. Trong Scrum, ba trụ cột hỗ trợ cách làm này là:

- **Minh bạch:** Những khía cạnh quan trọng của công việc và sản phẩm phải đủ rõ để người chịu trách nhiệm có cùng cơ sở hiểu thực tế.
- **Kiểm tra:** Nhóm và các bên liên quan thường xuyên xem xét hiện trạng, sản phẩm và tiến trình hướng đến mục tiêu để phát hiện sai lệch hoặc cơ hội.
- **Thích nghi:** Khi bằng chứng cho thấy kết quả chưa phù hợp, họ điều chỉnh sản phẩm, kế hoạch hoặc cách làm kịp thời.

Ba trụ cột liên hệ trực tiếp:

~~~mermaid
flowchart LR
    A["Minh bạch: nhìn thấy thực tế"] --> B["Kiểm tra: xem bằng chứng"]
    B --> C["Thích nghi: thay đổi quyết định/hành động"]
    C --> D["Quan sát kết quả mới"]
    D --> A
~~~

Nếu thông tin sai, chậm hoặc bị che giấu, cuộc kiểm tra sẽ dẫn đến kết luận sai. Nếu nhìn thấy đúng nhưng không có người có quyền điều chỉnh, nhóm vẫn chưa học được thành hành động. **Minh bạch là điều kiện cần của việc kiểm tra có ý nghĩa, không phải mục tiêu tự thân.**

### Ví dụ mở đầu

Một đội phát triển tính năng **“Tiếp tục học”** cho nền tảng đào tạo trực tuyến. Trong buổi họp, có ba phát biểu:

> **Developer:** “Chúng ta đã làm xong 9/10 đầu việc.”
>
> **Tester:** “Luồng lưu tiến độ đang lỗi trên hai thiết bị và chưa được kiểm thử hồi quy.”
>
> **Product Owner:** “Khách hàng đang chờ bản có thể dùng để thử vào thứ Sáu.”

Ba phát biểu có thể cùng đúng nhưng tạo ra những cách hiểu khác nhau về chữ **“xong”**. Nếu báo “90% hoàn thành”, người nghe có thể tưởng tính năng sắp có thể sử dụng, trong khi lỗi còn lại làm hỏng hành vi cốt lõi.

Minh bạch tốt sẽ cho mọi người thấy: mục tiêu là gì, phần nào chạy được, chất lượng ra sao, điều gì đang chặn, mức độ chắc chắn về ngày giao và quyết định tiếp theo. Nhờ đó, Product Owner có thể chọn giảm phạm vi, bổ sung thời gian kiểm thử hoặc lùi đợt phát hành, thay vì ra quyết định dựa trên một tỷ lệ thiếu ngữ cảnh.

## 2. Minh bạch không đồng nghĩa với đưa mọi dữ liệu lên bảng

Một hệ thống có hàng nghìn ticket, biểu đồ và báo cáo vẫn có thể thiếu minh bạch nếu người đọc không trả lời được câu hỏi cần thiết.

**Thông tin minh bạch cần có năm thuộc tính:**

| Thuộc tính | Câu hỏi kiểm tra | Ví dụ đạt yêu cầu |
| --- | --- | --- |
| **Đúng và có căn cứ** | Thông tin lấy từ quan sát nào? Có thể kiểm chứng không? | “Đã vượt qua 18/20 ca kiểm thử hồi quy; hai ca lỗi đã liên kết với issue cụ thể.” |
| **Kịp thời** | Thông tin còn phản ánh tình hình hiện tại không? | Bảng công việc cập nhật khi ticket chuyển trạng thái; bản báo cáo ghi ngày chốt dữ liệu. |
| **Dễ hiểu, nhất quán** | Mọi người có dùng cùng định nghĩa cho “Done”, “đang làm”, “bị chặn” không? | Chỉ đưa ticket vào Done sau khi đạt Definition of Done đã thống nhất. |
| **Liên quan đến quyết định** | Người nhận có thể dùng thông tin này để quyết định gì? | Chất lượng luồng đăng nhập, rủi ro phát hành, dự báo ngày hoàn thành. |
| **Có chủ thể chịu trách nhiệm** | Ai cập nhật, xác minh và xử lý tín hiệu? | Developer cập nhật trở ngại; đội kiểm thử cập nhật kết quả; Product Owner quyết định ưu tiên. |

Ngược lại, các biểu hiện **minh bạch hình thức** thường là:

- Bảng công việc có nhiều cột nhưng trạng thái không được cập nhật.
- Tỷ lệ hoàn thành được tính từ số task đã đóng, bỏ qua các lỗi nghiêm trọng.
- Báo cáo màu xanh cho mọi hạng mục vì người báo cáo ngại nêu rủi ro.
- Dashboard chỉ có các con số đẹp nhưng không có định nghĩa, mốc thời gian hoặc xu hướng.
- Quyết định quan trọng được đưa ra trong cuộc trò chuyện riêng, không được ghi lại cho người cần biết.
- Khối lượng thông tin quá lớn khiến người đọc không phân biệt được tín hiệu cần hành động.

**Nguyên tắc:** Cung cấp **đúng thông tin, đúng người, đúng thời điểm, ở mức chi tiết phù hợp**. Minh bạch là khả năng nhìn thấy và hiểu thực tế để cùng quyết định; không phải yêu cầu công khai mọi chi tiết nội bộ hoặc mọi dữ liệu nhạy cảm.

## 3. Cần minh bạch những điều gì?

Với một sản phẩm phần mềm đang phát triển, thông tin quan trọng có thể chia thành sáu nhóm.

### 3.1. Mục tiêu và giá trị cần đạt

Đội cần biết **vì sao** đang làm một việc. Các bên liên quan cần hiểu kết quả mong muốn, chứ không chỉ danh sách tính năng.

Ví dụ:

- Mục tiêu sản phẩm: tăng khả năng học viên quay lại khóa học đang theo dõi.
- Giả thuyết: nút “Tiếp tục học” trên trang chủ làm giảm thời gian tìm lại bài học.
- Chỉ số kiểm chứng: tỷ lệ người dùng có tiến độ học mở lại bài từ trang chủ; thời gian họ tìm được bài.
- Điều chưa biết: hành vi có khác biệt đáng kể giữa điện thoại và máy tính hay không.

Mục tiêu cần đủ cụ thể để xem tiến triển, nhưng không nên tuyên bố chắc chắn rằng một tính năng sẽ làm tăng kết quả kinh doanh trước khi kiểm chứng.

### 3.2. Phạm vi và thứ tự ưu tiên

Product Backlog cần giúp người xem hiểu **việc nào quan trọng nhất hiện tại**, mục đích của việc đó, thông tin nào còn thiếu và những thay đổi thứ tự gần đây.

Ví dụ:

| Ưu tiên | Hạng mục | Giá trị mong muốn | Trạng thái hiểu biết |
| --- | --- | --- | --- |
| 1 | Lưu đúng vị trí bài học | Học viên không mất tiến độ | Đã xác nhận lỗi khi học trên hai thiết bị |
| 2 | Hiển thị nút “Tiếp tục học” trên di động | Dễ quay lại bài đang học | Có phản hồi thử nghiệm ban đầu; cần xác minh thêm |
| 3 | Hoạt ảnh khi hoàn thành bài | Tăng cảm giác hứng thú | Chưa có bằng chứng về tác động |

Backlog có thể thay đổi khi xuất hiện bằng chứng mới. Sự minh bạch nằm ở việc người có liên quan **hiểu lý do thay đổi**, không phải giữ cố định một danh sách để tạo cảm giác ổn định.

### 3.3. Trạng thái thực tế của công việc

Nhóm cần thấy từng hạng mục đang ở đâu, chờ ai và vì sao bị chặn. Một bảng trạng thái đơn giản có thể gồm:

~~~text
Sẵn sàng  →  Đang phát triển  →  Chờ review  →  Đang kiểm thử  →  Done
                     ↘ Bị chặn: chờ API hoặc quyết định nghiệp vụ
~~~

**Các định nghĩa phải rõ ràng**:

- **Sẵn sàng:** đủ thông tin để nhóm có thể bắt đầu theo chính sách của nhóm; không nhất thiết là một trạng thái bắt buộc trong Scrum.
- **Đang phát triển:** công việc đã được nhận thực hiện và chưa hoàn thành điều kiện chuyển bước.
- **Chờ review:** đã có thay đổi cần người có trách nhiệm xem xét; không nên báo đã hoàn tất.
- **Đang kiểm thử:** các kiểm tra theo yêu cầu đang diễn ra; lỗi phát hiện phải được phản ánh.
- **Done:** đáp ứng các tiêu chí hoàn thành chung, có chất lượng theo Definition of Done nếu dùng Scrum.
- **Bị chặn:** công việc không thể tiến triển do thiếu thông tin, quyền quyết định, hệ thống hoặc phụ thuộc; cần ghi lý do và người/nhóm có thể gỡ.

Với Kanban, các chính sách làm việc và **giới hạn WIP (work in progress — công việc đang làm)** giúp lộ điểm nghẽn. Ví dụ, “Chờ review” liên tục chứa nhiều ticket có tuổi chờ cao là tín hiệu cần phân tích năng lực review, không đơn thuần là lý do thúc ép người viết code.

### 3.4. Chất lượng và khả năng sử dụng

Thông tin tiến độ không đầy đủ nếu tách khỏi chất lượng. Cần biết:

- Phần chức năng nào đang hoạt động và đã được kiểm chứng.
- Tiêu chí chấp nhận và Definition of Done nào đã được đáp ứng.
- Lỗi nghiêm trọng còn mở, phạm vi ảnh hưởng và giải pháp tạm thời nếu có.
- Trạng thái kiểm thử, tích hợp, phát hành, khôi phục và vận hành liên quan.
- Những giới hạn đã biết, ví dụ bản hiện tại chưa xử lý đồng bộ giữa các thiết bị.

**Definition of Done** là tập điều kiện chất lượng chung để xác định increment đã hoàn thành. Trong Scrum, một Product Backlog Item không thể được coi là một phần của increment nếu chưa đáp ứng Definition of Done. Đội cần bảo đảm người có liên quan hiểu rõ tiêu chuẩn này; không được đổi tên ticket thành “Done” trong khi còn bỏ qua các điều kiện quan trọng.

Ví dụ, checklist chất lượng cho luồng tiếp tục học có thể yêu cầu: hành vi đúng theo tiêu chí chấp nhận, test quan trọng đạt, code review xong, không làm lộ tiến độ của tài khoản khác, và tài liệu vận hành được cập nhật khi có thay đổi cần thiết.

### 3.5. Rủi ro, phụ thuộc và bất định

Một báo cáo tốt nói được cả **điều chưa biết**. Ví dụ:

| Loại thông tin | Cách diễn đạt thiếu minh bạch | Cách diễn đạt có ích |
| --- | --- | --- |
| Rủi ro | “Mọi việc ổn.” | “API đồng bộ tiến độ còn lỗi; có nguy cơ chưa đạt tiêu chí chấp nhận vào thứ Sáu.” |
| Phụ thuộc | “Đang chờ bên khác.” | “Chờ đội định danh cung cấp môi trường kiểm thử; người phụ trách đã được liên hệ, cập nhật tiếp vào chiều thứ Tư.” |
| Dự báo | “Chắc chắn xong tuần này.” | “Nếu API được sửa trước thứ Tư và kiểm thử hồi quy đạt, có khả năng giao thứ Sáu; hiện còn hai điều kiện chưa xác nhận.” |
| Giả định | “Người dùng thích chức năng này.” | “Ba trong năm người thử thấy tính năng hữu ích; mẫu nhỏ, cần thử thêm.” |
| Quyết định | “Đã thống nhất.” | “Product Owner ưu tiên sửa lỗi dữ liệu trước hiệu ứng; lý do là lỗi ảnh hưởng mục tiêu Sprint.” |

Đưa tin xấu sớm cho phép thay đổi có kiểm soát. Trì hoãn vì sợ làm ảnh hưởng báo cáo thường khiến chi phí sửa và chi phí truyền thông tăng.

### 3.6. Kết quả và bài học sau phản hồi

Một increment có thể chạy tốt nhưng không tạo ra tác động mong đợi. Nhóm nên minh bạch cả **kết quả sản phẩm**:

- Người dùng đã thử phần nào và gặp khó khăn gì?
- Giả thuyết nào được ủng hộ, chưa đủ bằng chứng hoặc bị bác bỏ?
- Kết quả đo thay đổi ra sao, trong khoảng thời gian và nhóm người dùng nào?
- Quyết định nào trong backlog đã thay đổi sau review?

Ví dụ: tăng số lần nhấn nút “Tiếp tục học” chưa đủ để kết luận tỷ lệ hoàn thành khóa học tăng; cần quan sát chỉ số kết quả dài hơn và kiểm tra các yếu tố gây nhiễu.

## 4. Ai cần biết thông tin nào?

Cùng một thực tế có thể được trình bày ở độ chi tiết khác nhau theo câu hỏi của người nhận. Điều này giúp dễ hiểu mà không làm méo thông tin.

| Người/nhóm liên quan | Câu hỏi thường cần trả lời | Hình thức phù hợp |
| --- | --- | --- |
| **Developers, QA, UX, vận hành** | Việc nào cần làm tiếp? Đang bị chặn ở đâu? Chất lượng có đạt? | Bảng công việc, pipeline CI, kết quả test, trao đổi kỹ thuật, log có quyền truy cập |
| **Product Owner hoặc người quyết định ưu tiên** | Điều gì tạo giá trị? Phạm vi nào có thể giao? Rủi ro nào buộc đổi ưu tiên? | Product Backlog, mục tiêu, increment, phản hồi khách hàng, rủi ro và dự báo |
| **Khách hàng/người dùng đại diện** | Phần nào có thể trải nghiệm? Kết quả đáp ứng nhu cầu đến đâu? | Demo luồng thật, các tiêu chí được xác nhận, giới hạn đã biết, kế hoạch lấy phản hồi |
| **Quản lý/chủ đầu tư** | Khả năng đạt mục tiêu, mốc giao và chi phí/rủi ro ra sao? | Tóm tắt kết quả, xu hướng giao hàng, các điều kiện của dự báo, vấn đề cần quyết định |
| **An toàn, bảo mật, pháp lý, kiểm toán** | Điều kiện bắt buộc và bằng chứng đã đáp ứng chưa? | Hồ sơ kiểm tra, truy vết, quyền phê duyệt, bằng chứng có kiểm soát truy cập |

Không nên lập năm phiên bản “sự thật” với định nghĩa hoặc số liệu mâu thuẫn. Các bản trình bày khác nhau nên truy về **cùng nguồn dữ liệu và cùng quy ước đo lường**. Ví dụ, trạng thái “Done” trong báo cáo quản lý không được bao gồm các ticket mà bảng kỹ thuật vẫn đang ghi “Chờ kiểm thử”.

### Minh bạch có giới hạn trách nhiệm

Đưa mọi dữ liệu ra công khai có thể tạo hại. Dữ liệu cá nhân của học viên, thông tin thanh toán, khóa truy cập, thông tin lỗ hổng chưa xử lý và hồ sơ nhân sự cần được bảo vệ theo quyền hạn. Nhóm vẫn có thể minh bạch **tình trạng và tác động** bằng cách:

- Thông báo “Có lỗi phân quyền nghiêm trọng đang xử lý; phát hành tạm dừng” cho bên liên quan.
- Chia sẻ chi tiết khai thác lỗi chỉ trong nhóm ứng cứu có quyền truy cập.
- Dùng dữ liệu tổng hợp hoặc ẩn danh để trình bày hành vi người dùng.
- Ghi rõ ai có thể xem bằng chứng gốc và quy trình xin quyền truy cập khi cần.

**Minh bạch không đồng nghĩa bỏ bảo mật, quyền riêng tư hoặc trách nhiệm nghề nghiệp.**

## 5. Dùng các thành phần Scrum để tạo cùng một bức tranh thực tế

Trong Scrum, những artefact và cam kết đi kèm giúp tạo sự minh bạch để kiểm tra và thích nghi. Mỗi artefact có một cam kết gắn với nó:

| Artefact Scrum | Cam kết | Điều cần minh bạch |
| --- | --- | --- |
| **Product Backlog** | **Product Goal** | Mục tiêu sản phẩm, thứ tự công việc, nhu cầu mới và lý do ưu tiên |
| **Sprint Backlog** | **Sprint Goal** | Mục tiêu Sprint, kế hoạch thực hiện đang được cập nhật, trở ngại ảnh hưởng mục tiêu |
| **Increment** | **Definition of Done** | Phần sản phẩm thực sự tích hợp được, chất lượng đáp ứng tiêu chuẩn, phần chưa hoàn thành |

### 5.1. Product Backlog: minh bạch “vì sao và điều gì tiếp theo”

Product Backlog là danh sách có thứ tự, phát triển liên tục, chứa những việc cần để cải tiến sản phẩm. Không nên hiểu rằng mọi hạng mục phải có ước lượng chi tiết và đặc tả hoàn chỉnh từ đầu. Các hạng mục gần thực hiện thường cần được làm rõ hơn các ý tưởng dài hạn.

**Ví dụ:** Product Goal là “Giúp học viên tiếp tục việc học dễ dàng hơn”. Product Backlog ưu tiên ổn định dữ liệu tiến độ trước khi thêm trò chơi hóa, vì lỗi dữ liệu có thể làm tính năng vô dụng. Product Owner cần giải thích được **căn cứ ưu tiên**, kể cả những dữ liệu chưa đủ chắc.

### 5.2. Sprint Backlog: minh bạch “chúng ta sẽ đạt mục tiêu bằng cách nào”

Sprint Backlog không chỉ là danh sách được chốt ở Sprint Planning rồi đóng băng. Developers điều chỉnh kế hoạch khi học thêm trong Sprint để hướng tới Sprint Goal.

Ví dụ nội dung cập nhật ngắn:

> **Sprint Goal:** Học viên mở lại được bài đang học và không mất tiến độ.
>
> **Đã xác minh:** Luồng trên một thiết bị hoạt động và các bài kiểm thử chính đạt.
>
> **Đang làm:** Xử lý tình huống mở cùng khóa học trên hai thiết bị.
>
> **Trở ngại:** Đang chờ API phiên bản mới từ nhóm định danh.
>
> **Rủi ro:** Nếu API trễ hơn thứ Tư, mục tiêu có thể không đạt trong Sprint này.
>
> **Hành động:** Developer phối hợp nhóm API hôm nay; Product Owner xem phương án giảm phạm vi nếu điều kiện không được đáp ứng.

Thông tin trên cho phép mọi người kiểm tra tiến trình theo **mục tiêu** thay vì chỉ đếm số ticket.

### 5.3. Increment và Definition of Done: minh bạch “đã dùng được chưa”

Một bản demo chạy được trong điều kiện thuận lợi chưa chắc là increment đạt Definition of Done. Khi review, hãy phân biệt rõ:

- Chức năng nào đáp ứng Definition of Done và có thể được dùng theo phạm vi dự kiến.
- Chức năng nào chỉ là nguyên mẫu, thử nghiệm hoặc công việc chưa xong.
- Những giới hạn còn tồn tại và điều kiện cần trước khi phát hành.

Trong Scrum, Sprint Review là dịp để Scrum Team và các bên liên quan xem kết quả Sprint, thảo luận điều đã thay đổi và cân nhắc thích nghi. **Không cần chờ Sprint Review mới minh bạch vấn đề**, và không biến cuộc họp thành nghi thức trình chiếu để che các phần chưa làm được.

### 5.4. Các sự kiện là cơ hội kiểm tra, không phải công cụ trình diễn báo cáo

| Sự kiện | Minh bạch thông tin nào? | Quyết định hoặc điều chỉnh mong đợi |
| --- | --- | --- |
| **Sprint Planning** | Mục tiêu giá trị, thứ tự backlog, năng lực, rủi ro và những gì đã biết | Xác định Sprint Goal và kế hoạch ban đầu khả thi |
| **Daily Scrum** | Tiến triển hướng Sprint Goal, vấn đề đang chặn, việc cần phối hợp | Developers điều chỉnh kế hoạch cho ngày làm việc tiếp theo |
| **Sprint Review** | Increment, phản hồi, bối cảnh kinh doanh mới, kết quả đã kiểm chứng | Điều chỉnh hướng sản phẩm và Product Backlog khi cần |
| **Sprint Retrospective** | Điểm nghẽn về tương tác, kỹ thuật, chất lượng, quy trình | Chọn cải tiến cụ thể và đánh giá hiệu quả trong thời gian tới |

Minh bạch tốt giúp mỗi sự kiện tạo ra **một câu hỏi hoặc quyết định có ích**. Việc lặp lại các con số không dẫn tới hành động không phải là mục tiêu của các sự kiện.

## 6. Minh bạch dòng công việc bằng Kanban

Kanban tập trung vào việc nhìn thấy và cải thiện **dòng giá trị qua hệ thống làm việc**. Nhóm có thể dùng Kanban khi bảo trì, xử lý yêu cầu vận hành, hoặc kết hợp các thực hành quản lý dòng việc trong quá trình phát triển sản phẩm.

### 6.1. Từ bảng trạng thái đến chính sách rõ ràng

Một bảng Kanban chỉ có ích nếu nhóm thống nhất:

1. **Đơn vị công việc:** Một thẻ đại diện cho yêu cầu, lỗi, luồng giá trị hay việc kỹ thuật?
2. **Điểm bắt đầu/kết thúc:** Khi nào một việc được coi đã bắt đầu và hoàn tất?
3. **Quy tắc chuyển cột:** Chẳng hạn vào “Chờ review” khi PR đã sẵn sàng; vào “Done” khi các tiêu chí chất lượng đạt.
4. **Giới hạn WIP:** Bao nhiêu việc được làm song song trước khi nhóm cần hoàn thành hoặc gỡ tắc?
5. **Chính sách công việc khẩn:** Loại việc nào được vượt thứ tự thông thường và ai có quyền kích hoạt?
6. **Cách làm hiện rõ trở ngại:** Gắn nhãn bị chặn, nguyên nhân, tuổi chờ, người phụ trách xử lý.

### 6.2. Ví dụ bảng Kanban minh họa

| Sẵn sàng | Đang phát triển (WIP ≤ 2) | Chờ review (WIP ≤ 2) | Kiểm thử (WIP ≤ 2) | Done |
| --- | --- | --- | --- | --- |
| Thông báo lỗi đăng nhập | Lưu tiến độ hai thiết bị | Thêm kiểm tra quyền xem khóa học | Test đường học offline | Sửa lỗi hiển thị khóa học |
| Bổ sung nhãn truy cập | Sửa nút trên di động | **Bị chặn:** chờ người review API (2 ngày) |  | Cập nhật hướng dẫn ghi danh |

Các giới hạn WIP ở đây **chỉ là giá trị ví dụ**. Khi thấy cột “Chờ review” đầy, nhóm nên hỗ trợ hoàn thành việc đang chờ trước khi bắt đầu thêm nhiều việc mới.

### 6.3. Chỉ số giúp nhìn thấy dòng việc

| Chỉ số | Ý nghĩa | Lưu ý diễn giải |
| --- | --- | --- |
| **Work in Progress (WIP)** | Số việc đã bắt đầu nhưng chưa hoàn thành theo quy ước | WIP cao có thể làm tăng chuyển ngữ cảnh; giới hạn phải phù hợp năng lực và loại công việc |
| **Throughput** | Số việc hoàn tất trong một khoảng thời gian | Chỉ có ý nghĩa khi quy tắc chia việc và cách đếm tương đối nhất quán |
| **Cycle time** | Thời gian từ mốc bắt đầu thực hiện đến mốc hoàn thành theo định nghĩa nhóm | Nên xem phân bố và các việc ngoại lệ, không chỉ giá trị trung bình |
| **Lead time** | Thời gian từ mốc ghi nhận/đề nghị đến mốc giao, tùy quy ước | Điểm bắt đầu khác cycle time; phải nêu quy ước rõ |
| **Work item age** | Thời gian một việc đang làm đã tồn tại từ lúc bắt đầu đến hiện tại | Hữu ích để phát hiện việc đang bị bỏ quên trước khi hoàn thành |

**Ví dụ tính thời gian (ngày lịch):** Một yêu cầu được ghi nhận lúc 10:00 ngày 2/6, bắt đầu phát triển lúc 10:00 ngày 5/6 và hoàn thành lúc 10:00 ngày 10/6.

- **Lead time = 8 ngày**, tính từ lúc ghi nhận đến hoàn thành.
- **Cycle time = 5 ngày**, tính từ lúc bắt đầu thực hiện đến hoàn thành.
- Ba ngày đầu là thời gian chờ trước khi bắt đầu theo quy ước này.

Đây là dữ liệu của **một hạng mục**, không đại diện cho dự báo chung. Muốn dự báo có căn cứ, cần theo dõi nhiều hạng mục cùng kiểu công việc, quan sát biến động, phụ thuộc và các điều kiện thay đổi.

### 6.4. Tìm nguyên nhân thay vì thưởng phạt con số

Nếu throughput tăng nhưng lỗi sản xuất cũng tăng, không thể vội kết luận quy trình tốt hơn. Nếu cycle time giảm vì nhóm chỉ nhận các ticket dễ, điều đó chưa nói lên giá trị của sản phẩm. Dùng chỉ số để **đặt câu hỏi và thử cải tiến**, không để theo dõi hiệu suất cá nhân hay ép người làm tăng lượng ticket.

## 7. Minh bạch kỹ thuật: làm rõ “phần mềm hoạt động” bằng bằng chứng

Minh bạch nghiệp vụ cần đi cùng minh bạch kỹ thuật. Nếu mọi bảng điều khiển đều báo đúng tiến độ nhưng pipeline build hỏng hoặc phát hành gây lỗi nghiêm trọng, bức tranh vẫn sai lệch.

Các thực hành của **Extreme Programming (XP)** có thể hỗ trợ:

- **Tích hợp liên tục (CI):** Kết quả build và kiểm thử được phản hồi sớm, giúp lỗi tích hợp dễ nhìn thấy.
- **Kiểm thử tự động/TDD khi phù hợp:** Làm rõ hành vi mong đợi và cung cấp bằng chứng có thể chạy lại.
- **Pair programming và review:** Chia sẻ hiểu biết, phát hiện giả định khác nhau trước khi thành lỗi.
- **Refactor thường xuyên:** Giảm chi phí thay đổi và làm rõ rủi ro kỹ thuật, với điều kiện có kiểm thử bảo vệ.

Nhóm có thể hiển thị trạng thái pipeline, tần suất build lỗi, lỗi kiểm thử hồi quy, issue chất lượng nghiêm trọng và mức sẵn sàng triển khai. Nhưng cần diễn giải đúng:

- “Pipeline xanh” chỉ chứng minh **những kiểm tra đã định nghĩa** đang đạt, không chứng minh không còn lỗi.
- “100% test pass” không cho biết các trường hợp quan trọng đã được kiểm thử đầy đủ hay chưa.
- “Đã deploy lên staging” không đồng nghĩa đã phát hành cho khách hàng.
- “Có thể demo” không đồng nghĩa đáp ứng bảo mật, tính chính xác dữ liệu và Definition of Done.

**Ví dụ:** Bộ test có 200 ca đều đạt nhưng thiếu trường hợp hai thiết bị ghi tiến độ cùng lúc. Khi người dùng gặp lỗi, không nên báo “test đầy đủ 100%”; cần cập nhật test case, đánh giá phạm vi ảnh hưởng và giải thích lỗ hổng bằng chứng.

## 8. Phân biệt dữ kiện, suy luận, giả định, dự báo và cam kết

Đây là một kỹ năng quan trọng để tránh tạo ảo tưởng chắc chắn. Các loại phát biểu khác nhau cần được gắn nhãn rõ.

| Loại phát biểu | Ý nghĩa | Ví dụ |
| --- | --- | --- |
| **Dữ kiện đã quan sát** | Sự kiện có thể kiểm tra từ nguồn và mốc thời gian cụ thể | “Trong lần chạy CI lúc 14:00, 2/40 bài kiểm thử thất bại.” |
| **Suy luận** | Cách giải thích dữ kiện; có thể đúng hoặc sai | “Lỗi có thể do thay đổi API tuần này.” |
| **Giả định** | Điều chưa được xác minh nhưng đang dùng để quyết định | “API mới sẽ sẵn sàng trước thứ Tư.” |
| **Dự báo** | Ước lượng kết quả tương lai có điều kiện, mang bất định | “Nếu API đến đúng hẹn và test đạt, đội dự kiến có thể review vào thứ Sáu.” |
| **Cam kết/quyết định** | Điều người có thẩm quyền đồng ý thực hiện hoặc chịu trách nhiệm | “Đội sẽ chạy bộ kiểm thử hồi quy trước khi đề xuất phát hành.” |

### Vì sao cần phân biệt?

Nếu một giả định bị kể lại như dữ kiện, lãnh đạo có thể ra quyết định đầu tư hoặc công bố ngày giao thiếu cơ sở. Nếu một dự báo được hiểu thành cam kết tuyệt đối, nhóm có thể che lỗi để “giữ lời”. Minh bạch đòi hỏi nói rõ điều kiện, độ tin cậy và phương án khi điều kiện không đạt.

Ví dụ cách báo cáo tiến độ:

> “Luồng tiếp tục học đã chạy trên một thiết bị và qua kiểm thử cơ bản. Phần đồng bộ hai thiết bị đang lỗi; nguyên nhân có thể nằm ở API lưu tiến độ nhưng chưa xác nhận. Nhóm đã đề nghị hỗ trợ từ đội API và sẽ báo kết quả điều tra vào ngày mai. Mốc phát hành thứ Sáu đang có rủi ro; Product Owner cần cân nhắc phát hành giới hạn hoặc lùi để bảo đảm đúng dữ liệu.”

Đoạn này có dữ kiện, giả thuyết, hành động, rủi ro và quyết định cần đưa ra. Nó hữu ích hơn “Đang đúng kế hoạch” khi chưa đủ bằng chứng.

### Báo cáo bằng khoảng và điều kiện

Trong công việc bất định, một ngày dự kiến duy nhất thường dễ bị hiểu là chắc chắn. Nếu có dữ liệu đáng tin, nhóm có thể dùng khoảng dự báo hoặc phân vị thời gian hoàn thành; nếu dữ liệu ít, hãy nêu điều kiện và độ bất định một cách định tính. Không tự gán xác suất “95% hoàn thành” nếu không có phương pháp hoặc dữ liệu hỗ trợ.

**Quy tắc:** Tăng độ chính xác của thông tin trước khi tăng độ chính xác của con số.

## 9. Minh bạch để nhận phản hồi sớm, không để đánh giá con người

Một nhóm chỉ nói thật khi có đủ an toàn tâm lý để nêu vấn đề mà không mặc nhiên bị đổ lỗi. Nếu mọi lỗi bị biến thành chỉ tiêu phạt, người làm có động cơ che giấu hoặc chuyển lỗi sang người khác. Điều đó phá vỡ chất lượng của thông tin.

Thói quen nên nuôi dưỡng:

1. **Nêu sự kiện trước khi diễn giải:** “PR đang chờ review hai ngày” thay vì “anh A làm chậm cả đội”.
2. **Tập trung vào cơ chế công việc:** Có quá nhiều WIP? Quy tắc review mơ hồ? Thiếu người xác nhận nghiệp vụ?
3. **Đặt câu hỏi mở:** “Chúng ta còn thiếu thông tin gì để quyết định?” thay vì “Ai chịu trách nhiệm cho con số đỏ?”.
4. **Ghi quyết định sau khi trao đổi:** Mọi người hiểu ai làm gì và thời điểm xem lại.
5. **Bảo vệ quyền riêng tư:** Chia sẻ trạng thái hệ thống và tác động cần thiết, không công khai dữ liệu cá nhân hoặc thông tin không liên quan.

Minh bạch không cần diễn ra bằng cuộc họp dài. Một dashboard dùng chung có thể giảm hỏi lặp; cuộc trò chuyện ngắn có thể giải quyết điểm mơ hồ mà dashboard không giải thích được.

### Phản hồi và các rủi ro về quyền lực

Product Owner, trưởng nhóm kỹ thuật, người kiểm thử và khách hàng có góc nhìn khác nhau. Khi có tranh chấp, cần một **nguồn thông tin chung** và quy tắc quyết định minh bạch. Ví dụ:

- Tester phản đối phát hành vì thiếu test bảo mật quan trọng: phải xem rủi ro và tiêu chí hoàn thành, không chỉ áp lực kinh doanh.
- Product Owner muốn đổi ưu tiên: phải giải thích mục tiêu mới và ảnh hưởng lên phạm vi, phụ thuộc, chất lượng.
- Developer báo nợ kỹ thuật: cần mô tả tác động quan sát được (lỗi tái diễn, thời gian thay đổi, rủi ro phục hồi), không chỉ nói “code xấu”.

Thông tin hữu ích giúp mọi người **phản biện dựa trên bằng chứng**, không biến khác biệt vị trí thành cuộc tranh cãi cá nhân.

## 10. Thiết kế bảng thông tin phù hợp từng quyết định

Không có dashboard duy nhất đúng cho mọi tổ chức. Bắt đầu từ câu hỏi: **Ai cần quyết định điều gì, với thông tin nào, bao lâu cần cập nhật?**

### 10.1. Bảng theo dõi hằng ngày cho nhóm

| Mục | Nội dung minh họa |
| --- | --- |
| Mục tiêu hiện tại | Học viên tiếp tục bài đang học chính xác trên thiết bị thường dùng |
| Đã Done theo quy ước | Luồng lưu/đọc trên một thiết bị; test nghiệp vụ cơ bản |
| Đang làm | Đồng bộ tiến độ giữa hai thiết bị |
| Bị chặn | Chờ xác định cách xử lý xung đột ghi tiến độ; người phụ trách: nhóm API |
| Chất lượng | Hai test đồng bộ đang thất bại; chưa đáp ứng Definition of Done toàn tính năng |
| Việc cần quyết định | Chọn quy tắc tiến độ khi hai thiết bị cập nhật khác nhau |
| Mốc kiểm tra lại | Sau buổi phối hợp với nhóm API và sau lần chạy CI kế tiếp |

Đây là một **ví dụ minh họa**, không phải báo cáo tình trạng dự án có thật. Khi dùng thực tế, cần cập nhật đúng giờ và nguồn dữ liệu hiện tại.

### 10.2. Bản tóm tắt cho bên liên quan

Nên ngắn, hướng vào quyết định:

> **Mục tiêu:** Giảm khó khăn khi học viên quay lại bài đã học.
>
> **Kết quả đã kiểm chứng:** Luồng trên một thiết bị hoạt động; nhóm dùng thử đã nhìn thấy nút tiếp tục học trên trang chủ.
>
> **Điều còn chưa đạt:** Đồng bộ giữa hai thiết bị có lỗi dữ liệu; chưa đạt tiêu chí chất lượng để phát hành cho toàn bộ người dùng.
>
> **Rủi ro và điều kiện:** Cần xác nhận cách xử lý xung đột tiến độ và kiểm thử lại trước ngày dự kiến.
>
> **Quyết định đề nghị:** Ưu tiên sửa dữ liệu trước hoạt ảnh; chỉ phát hành khi tiêu chí hoàn thành được đáp ứng.
>
> **Lần cập nhật tiếp:** Sau khi có kết quả kiểm thử đồng bộ.

Thông điệp trên để người đọc biết **cái gì đang đúng, cái gì chưa chắc, có thể quyết định gì**, thay vì nhận một nhãn “xanh/vàng/đỏ” mà không có lời giải thích.

### 10.3. Cơ chế duy trì

- **Nguồn dữ liệu:** Xác định ticket board, kho mã nguồn, pipeline CI, kết quả test, đo lường sản phẩm và người chịu trách nhiệm mỗi nguồn.
- **Định nghĩa chung:** Thống nhất cách tính Done, lead time, ngày chốt dữ liệu và mức nghiêm trọng của lỗi.
- **Nhịp cập nhật:** Cập nhật theo thay đổi trạng thái quan trọng; chọn lịch tóm tắt phù hợp với nhịp ra quyết định.
- **Quyền xem:** Phân quyền dữ liệu nhạy cảm; cung cấp trạng thái tổng hợp cho người cần biết.
- **Hành động tiếp theo:** Mỗi tín hiệu cảnh báo cần có cách xử lý hoặc người đánh giá rõ, tránh dashboard chỉ để trưng bày.

Khi bảng đã đủ tốt, câu hỏi của bên liên quan sẽ chuyển từ “Đang làm tới đâu?” sang “Bằng chứng này cho thấy nên đổi điều gì?”.

## 11. Tình huống tổng hợp: từ báo cáo đẹp đến quyết định đúng

### Bối cảnh

Một đội gồm Product Owner, Developers, QA và người phụ trách hạ tầng xây dựng chức năng đăng ký khóa học trả phí. Cuối Sprint, báo cáo tóm tắt ghi:

> “Hoàn thành 18/20 ticket (90%); tiến độ xanh; dự kiến phát hành thứ Sáu.”

Tuy nhiên:

- Hai ticket chưa xong là **đối soát thanh toán** và **xử lý yêu cầu thanh toán gửi lại**.
- Chưa xác nhận được cách khôi phục nếu cổng thanh toán bên ngoài trả trạng thái muộn.
- Môi trường kiểm thử của đối tác đôi khi không sẵn sàng.
- Mười tám ticket còn lại có nhiều việc về giao diện, tài liệu và cấu hình.

### Phân tích

**Báo cáo 90% có đúng không?** Có thể đúng nếu chỉ đếm số ticket. Nhưng nó **không đủ để kết luận sản phẩm sẵn sàng phát hành**, bởi hai hạng mục còn lại có thể quyết định tính chính xác tài chính và an toàn giao dịch. Người đọc dễ đồng nhất tỷ lệ ticket đóng với tỷ lệ giá trị hoặc mức sẵn sàng.

**Thông tin cần làm rõ:**

1. Mục tiêu tối thiểu của đợt phát hành là gì?
2. Những luồng thanh toán nào đã chạy qua kiểm thử đầu đến cuối?
3. Definition of Done có yêu cầu kiểm thử lặp giao dịch, đối soát và xử lý trạng thái chậm không?
4. Những phụ thuộc nào do đối tác kiểm soát và có phương án thử thay thế nào?
5. Nếu không kịp điều kiện chất lượng, có phương án giới hạn phát hành hoặc dời ngày nào?

### Bản báo cáo minh bạch hơn

| Hạng mục | Tình trạng thực tế | Tác động |
| --- | --- | --- |
| Giao diện đăng ký và chọn khóa | Đã kiểm thử theo tiêu chí đã thống nhất | Sẵn sàng cho kiểm thử tích hợp |
| Luồng thanh toán một lần | Đã qua các test chính trên môi trường thử nghiệm | Có bằng chứng một phần, chưa đủ cho mọi trường hợp |
| Đối soát và gửi lại yêu cầu | Chưa đạt tiêu chí chấp nhận | **Chặn quyết định phát hành** |
| Môi trường đối tác | Có thời điểm không sẵn sàng | Nguy cơ ảnh hưởng mốc kiểm chứng |
| Dự báo thứ Sáu | Phụ thuộc kết quả test tích hợp và đối soát | Chưa thể xem là cam kết chắc chắn |
| Quyết định cần đưa ra | Giữ cổng kiểm soát chất lượng; ưu tiên hỗ trợ tích hợp | Product Owner và bên chịu trách nhiệm phát hành cùng đánh giá |

Sau buổi kiểm tra, nhóm có thể quyết định dừng mở rộng phạm vi, ưu tiên hoàn thiện luồng thanh toán an toàn và làm rõ mốc phát hành sau khi test đạt. Việc nói rõ rủi ro **không làm dự án thất bại**; nó cho phép đội tránh một phát hành có hậu quả lớn.

### Liên hệ ba trụ cột

- **Minh bạch:** Lỗi, điều kiện Done và phụ thuộc được nhìn thấy rõ hơn số “90%”.
- **Kiểm tra:** Đội và các bên liên quan xem bằng chứng test, luồng giao dịch và trạng thái đối tác.
- **Thích nghi:** Điều chỉnh phạm vi hoặc mốc phát hành, bổ sung kiểm thử và kế hoạch xử lý phụ thuộc.

## 12. Các lỗi thường gặp và cách khắc phục

| Lỗi thường gặp | Vì sao gây hại | Cách cải thiện |
| --- | --- | --- |
| Báo tỷ lệ % hoàn thành không có định nghĩa | Dễ bị hiểu là mức sẵn sàng hoặc giá trị hoàn thành | Báo theo increment/Definition of Done và rủi ro còn mở |
| Chỉ chia sẻ tin tốt | Người quyết định phát hiện vấn đề quá muộn | Nêu sự kiện, tác động, mức chưa chắc chắn và hành động đang làm |
| Mỗi nhóm dùng một định nghĩa Done | Không thể so sánh hay tổng hợp đúng | Thống nhất tiêu chuẩn, làm rõ ngoại lệ và phạm vi |
| Không cập nhật trạng thái công việc | Dashboard phản ánh quá khứ, không phản ánh hiện tại | Cập nhật ngay khi đổi trạng thái; ghi thời điểm dữ liệu |
| Chỉ đếm task hoặc story point | Không cho biết giá trị người dùng hay chất lượng | Kết hợp tín hiệu giá trị, dòng công việc và lỗi |
| Số liệu trở thành công cụ trách phạt | Khuyến khích che lỗi và tối ưu chỉ số hình thức | Dùng dữ liệu để tìm điểm nghẽn ở cấp hệ thống |
| Trộn giả định với sự kiện | Dự báo bị hiểu thành cam kết chắc chắn | Đánh dấu điều đã quan sát, điều chưa biết và điều kiện dự báo |
| Chia sẻ tràn lan thông tin nhạy cảm | Rủi ro bảo mật và quyền riêng tư | Phân quyền, ẩn danh và chia sẻ tình trạng ở mức cần thiết |
| Có dữ liệu nhưng không có quyết định | Kiểm tra trở thành hình thức | Nêu lựa chọn, người quyết định, thời hạn và chỉ số kiểm chứng |

## 13. Bài tập thực hành

### Bài tập 1 — Viết lại báo cáo tiến độ

Một nhóm gửi báo cáo: “Sprint đạt 95%; chỉ còn hai lỗi nhỏ; mọi việc đúng tiến độ.” Thông tin bổ sung:

- Một lỗi khiến học viên không ghi nhận được bài đã hoàn thành trên điện thoại.
- Lỗi còn lại là nhãn nút bị lệch vài pixel.
- Khách hàng sẽ thử bản mới sau hai ngày, nhưng chưa xác định được thời gian sửa lỗi đầu.

**Yêu cầu:** Viết bản cập nhật tối đa 120 từ, có (a) dữ kiện đã biết, (b) tác động lên mục tiêu, (c) bất định, (d) đề xuất ưu tiên và (e) thời điểm kiểm tra tiếp.

**Gợi ý:** Không gom hai lỗi thành “nhỏ”. Lỗi mất tiến độ ảnh hưởng trực tiếp giá trị; cần xác minh mức nghiêm trọng và tiêu chí phát hành. Lỗi hiển thị có thể xếp sau tùy mức ảnh hưởng khả năng sử dụng.

### Bài tập 2 — Chọn tín hiệu cho bảng Kanban

Nhóm có 10 việc “Đang làm”, 7 việc “Chờ review” và chỉ hoàn tất 2 việc trong tuần. Người quản lý yêu cầu “mọi người phải nhận nhiều ticket hơn”.

**Yêu cầu:** Nêu ít nhất ba câu hỏi kiểm tra trước khi thay đổi cách làm, cùng một thí nghiệm cải tiến nhỏ.

**Gợi ý:** Cần hỏi giới hạn WIP hiện tại, tuổi việc đang chờ, năng lực review, quy tắc chuyển cột và chất lượng sau review. Có thể thử giới hạn số việc bắt đầu mới và dành thời gian gỡ tồn đọng review; theo dõi work item age, cycle time và lỗi trong vài tuần.

### Bài tập 3 — Phân loại phát biểu

Phân loại các câu sau thành dữ kiện, suy luận, giả định, dự báo hoặc cam kết:

1. “Hôm qua, 4/50 yêu cầu thanh toán thử nghiệm thất bại.”
2. “Có lẽ lỗi do nhà cung cấp thay đổi định dạng phản hồi.”
3. “Nhà cung cấp sẽ cập nhật tài liệu API trước ngày mai.”
4. “Nếu API được sửa và kiểm thử đạt, nhóm dự kiến review vào thứ Sáu.”
5. “Nhóm sẽ ghi lại log cần thiết và đối chiếu toàn bộ giao dịch lỗi.”

**Đáp án tham khảo:** (1) dữ kiện nếu có nguồn log/test; (2) suy luận; (3) giả định nếu chưa có xác nhận đáng tin; (4) dự báo có điều kiện; (5) cam kết/hành động đã nhận. Một câu có thể đổi loại khi có thêm bằng chứng: thông báo chính thức từ nhà cung cấp có thể biến (3) thành thông tin về **cam kết của họ**, nhưng chưa bảo đảm việc giao thực tế sẽ diễn ra đúng ngày.

### Bài tập 4 — Chọn thông tin cho từng bên

Bạn là thành viên nhóm phát triển tính năng đăng ký khóa học. Hãy soạn:

- Một cập nhật cho Developers/QA về lỗi phân quyền, test thất bại và người phụ trách xử lý.
- Một cập nhật cho Product Owner về tác động lên giá trị và lựa chọn ưu tiên.
- Một cập nhật cho khách hàng về chức năng có thể trải nghiệm, giới hạn hiện tại và mốc thông báo tiếp.

**Ràng buộc:** Ba bản phải nhất quán về sự thật; không làm lộ dữ liệu học viên hoặc chi tiết khai thác lỗi bảo mật cho người không có quyền.

## 14. Checklist áp dụng vào công việc hằng ngày

Trước khi báo “hoàn thành”, “đúng tiến độ” hoặc “có thể phát hành”, hãy tự hỏi:

- [ ] Có nói rõ **mục tiêu hoặc giá trị** đang theo đuổi?
- [ ] Có bằng chứng cập nhật cho **phần mềm thực sự hoạt động** và tiêu chí chất lượng?
- [ ] Có phân biệt Done với đang kiểm thử, chờ review hoặc nguyên mẫu?
- [ ] Có làm rõ **rủi ro, phụ thuộc, việc bị chặn**, người chịu trách nhiệm và hành động tiếp theo?
- [ ] Có phân biệt **dữ kiện, giả định, dự báo và cam kết**?
- [ ] Các con số có **định nghĩa, phạm vi, nguồn và mốc thời gian**?
- [ ] Người nhận có thể hiểu **điều gì cần quyết định hoặc kiểm tra tiếp**?
- [ ] Thông tin được chia sẻ đúng quyền truy cập, bảo vệ dữ liệu nhạy cảm?
- [ ] Có kế hoạch quan sát kết quả sau khi quyết định để tiếp tục học hỏi?

Không cần áp dụng toàn bộ checklist cho mọi trao đổi nhỏ. Với một sự cố nghiêm trọng hoặc quyết định phát hành, độ rõ ràng của các câu trả lời này đặc biệt quan trọng.

## 15. Ghi nhớ

Minh bạch là khả năng **cùng nhìn đúng thực tế** về mục tiêu, công việc, sản phẩm, chất lượng và rủi ro. Nó tạo cơ sở để kiểm tra và thích nghi, giúp Agile phát huy giá trị qua phản hồi sớm, phát triển tăng dần và cải tiến liên tục.

- **Scrum** làm rõ mục tiêu và trạng thái bằng Product Backlog, Sprint Backlog, Increment cùng các cam kết Product Goal, Sprint Goal và Definition of Done.
- **Kanban** làm rõ dòng công việc, trạng thái bị chặn, WIP và thời gian hoàn thành để phát hiện điểm nghẽn.
- **Các thực hành XP** giúp tạo bằng chứng kỹ thuật về khả năng hoạt động, kiểm thử và chất lượng khi phần mềm liên tục thay đổi.
- **Bất định cần được nói rõ:** dữ kiện đã quan sát khác với giả định, dự báo và cam kết.
- **Thông tin chỉ thật sự hữu ích khi dẫn đến quyết định**, có người chịu trách nhiệm và được kiểm chứng bằng kết quả tiếp theo.

Câu hỏi quan trọng nhất khi công bố một trạng thái không phải “Bảng đã đủ xanh chưa?”, mà là: **“Từ bằng chứng hiện có, mọi người có hiểu cùng một thực tế và biết cần quyết định điều gì tiếp theo không?”**
