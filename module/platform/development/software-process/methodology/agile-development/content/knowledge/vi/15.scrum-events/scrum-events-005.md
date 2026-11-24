# Sprint Review để cùng kiểm tra kết quả và định hướng tiếp theo

## 1. Sprint Review không chỉ là buổi trình diễn cuối Sprint

Trong phát triển phần mềm, một nhóm có thể hoàn thành nhiều chức năng nhưng vẫn chưa biết chúng có giải quyết đúng nhu cầu của người dùng không. Nếu cuối mỗi chu kỳ nhóm chỉ trình chiếu các màn hình đã xây rồi nghe lời khen, các giả định ban đầu có thể tiếp tục tồn tại mà không được kiểm chứng. Nhóm sẽ có nhiều **đầu ra (output)** nhưng chưa chắc tạo ra **kết quả có giá trị (outcome)**.

Ví dụ, một Scrum Team phát triển nền tảng học trực tuyến đã thêm hành động “Tiếp tục học” trên trang khóa. Chức năng hoạt động đúng theo tiêu chí chấp nhận; tuy vậy, khi xem sản phẩm, đại diện hỗ trợ cho biết học viên thường không nhớ mình đã hoàn thành bài nào, còn giảng viên nhận thấy một số khóa cho phép học bài không theo thứ tự. Nhóm cần cùng các bên xem lại cách hiểu “bài tiếp theo”, phản hồi thực tế và hướng cải tiến, thay vì chỉ xác nhận nút đã xuất hiện.

**Sprint Review** là một sự kiện của Scrum nhằm **kiểm tra kết quả của Sprint và xác định những điều chỉnh cần thiết trong tương lai**. Scrum Team cùng các stakeholder quan trọng xem xét những gì đã đạt được, tiến triển hướng tới Product Goal và những thay đổi của môi trường sản phẩm. Trên cơ sở đó, các bên cộng tác tìm hướng đi tiếp theo; **Product Backlog có thể được điều chỉnh** để phản ánh cơ hội hoặc hiểu biết mới.

Sprint Review giúp thực hành cốt lõi của Agile: giao phần mềm có giá trị theo những lát tăng dần, nhận phản hồi sớm và thích ứng thay vì tiếp tục làm theo kế hoạch cũ bất kể kết quả. Đây không phải buổi “báo cáo thành tích”, không phải cổng duyệt bắt buộc trước khi phát hành và cũng không phải nơi chỉ nhận thêm danh sách yêu cầu.

> **Câu hỏi trung tâm của Sprint Review:** “Từ Increment và bằng chứng hiện có, chúng ta đã tiến gần Product Goal như thế nào; điều gì thay đổi trong bối cảnh, và bước tiếp theo đáng làm nhất là gì?”

## 2. Sprint Review nằm ở đâu trong Scrum?

Scrum hoạt động theo các **Sprint** có thời lượng cố định, tối đa một tháng. Mỗi Sprint bao gồm việc lập kế hoạch, thực hiện, kiểm tra, thích ứng và những sự kiện Scrum cần thiết. Sprint Review diễn ra gần cuối Sprint, **trước Sprint Retrospective**; Retrospective là sự kiện kết thúc Sprint. Một Sprint mới bắt đầu ngay khi Sprint trước kết thúc.

Theo Scrum Guide 2020, Sprint Review có **timebox tối đa bốn giờ cho Sprint dài một tháng**; với Sprint ngắn hơn, Review thường ngắn hơn. Đây là giới hạn thời gian, **không phải yêu cầu họp đủ bốn giờ**. Không có một chương trình nghị sự bắt buộc cho mọi Scrum Team: cách tổ chức cần phục vụ mục đích kiểm tra và thích ứng.

| Khía cạnh | Ý nghĩa đối với Sprint Review |
| --- | --- |
| **Mục đích** | Kiểm tra kết quả Sprint và xác định thích ứng tương lai |
| **Người tham gia chính** | Scrum Team và các stakeholder quan trọng được mời hợp tác |
| **Đối tượng kiểm tra** | Increment, kết quả đã đạt, tiến triển Product Goal và thay đổi bối cảnh |
| **Hình thức** | Buổi làm việc cộng tác, không giới hạn ở trình diễn một chiều |
| **Kết quả có thể có** | Hiểu biết chung, quyết định ưu tiên, giả thuyết mới, Product Backlog được điều chỉnh |
| **Giới hạn thời gian** | Tối đa bốn giờ cho Sprint một tháng; Sprint ngắn thường ngắn hơn |
| **Điều không phải** | Cổng ký duyệt chất lượng, cuộc họp báo cáo cấp trên, hoặc Sprint Retrospective |

### Ba trụ cột thực nghiệm hiện diện thế nào?

Scrum dựa trên **minh bạch (transparency)**, **kiểm tra (inspection)** và **thích ứng (adaptation)**:

1. **Minh bạch:** nhóm làm rõ điều gì đã đạt Definition of Done, điều gì chưa hoàn tất, dữ liệu nào đáng tin và điều gì còn là giả thuyết.
2. **Kiểm tra:** các bên nhìn vào phần mềm có thể sử dụng, phản hồi người dùng, chất lượng và tiến triển tới mục tiêu sản phẩm.
3. **Thích ứng:** Product Backlog hoặc cách tiếp cận sản phẩm được xem lại khi thông tin mới làm thay đổi lựa chọn tốt nhất.

Nếu mọi người nhìn thấy tính năng nhưng không thảo luận điều đã học hoặc quyết định tiếp theo, Review mới thực hiện được một phần mục đích. Nếu có nhiều ý tưởng mới nhưng không xem Increment và thực tế sử dụng, nhóm cũng khó có cơ sở để ưu tiên.

~~~mermaid
flowchart LR
    A["Sprint Goal và công việc trong Sprint"] --> B["Increment đạt Definition of Done"]
    B --> C["Sprint Review: cùng kiểm tra kết quả"]
    D["Người dùng và dữ liệu vận hành"] --> C
    E["Thay đổi về thị trường, chính sách, kỹ thuật"] --> C
    C --> F["Bài học, cơ hội và rủi ro"]
    F --> G["Điều chỉnh Product Backlog / hướng sản phẩm"]
    G --> H["Lập kế hoạch cho bước tiếp theo"]
    H -. "Tiếp tục học qua Sprint sau" .-> A
~~~

## 3. Ai tham gia và đóng góp điều gì?

Sprint Review là sự kiện của **Scrum Team và các stakeholder quan trọng**. Tập hợp người tham gia phụ thuộc nội dung Sprint và quyết định sản phẩm cần xem xét; không phải mọi buổi Review đều cần toàn bộ nhân sự công ty.

| Người tham gia | Đóng góp chính | Cần tránh |
| --- | --- | --- |
| **Product Owner** | Kết nối kết quả với Product Goal; làm rõ bối cảnh và thứ tự Product Backlog; lắng nghe phản hồi để ra quyết định giá trị | Chỉ đọc báo cáo điểm số hoặc tự biến Review thành buổi ký duyệt |
| **Developers** | Cho thấy Increment hoạt động thật, giải thích giới hạn, bằng chứng kiểm thử và các phương án kỹ thuật | Chỉ trình bày task đã làm, che giấu hạng mục chưa Done |
| **Scrum Master** | Giúp Scrum Team và tổ chức hiểu mục đích, hỗ trợ sự kiện hữu ích và không vượt timebox | Tự quyết định nội dung ưu tiên thay Product Owner hoặc biến buổi họp thành nghi thức hình thức |
| **Người dùng/đại diện khách hàng** | Chia sẻ tình huống thực, giá trị sử dụng, khó khăn và kỳ vọng có căn cứ | Chỉ phản hồi sở thích cá nhân rồi mặc định đại diện mọi người dùng |
| **Stakeholder kinh doanh, hỗ trợ, vận hành, bảo mật, pháp lý...** | Cập nhật ràng buộc, thay đổi thị trường, tác động vận hành hoặc rủi ro cần xử lý | Áp danh sách yêu cầu trực tiếp cho từng Developer trong Review |

**Product Owner là một người, không phải một ủy ban.** Stakeholder có thể đề xuất và cung cấp bằng chứng; PO chịu trách nhiệm giải trình về quản lý Product Backlog hiệu quả, trong đó có thứ tự PBIs. Scrum Team cùng xem xét khả năng thực thi và hệ quả. Một ý tưởng được nêu tại Review **chưa tự động trở thành cam kết của Sprint tiếp theo**.

### Mời người có khả năng tạo ra thông tin hữu ích

Nếu Sprint cải thiện luồng đăng ký khóa học, nên có người hiểu hành trình đăng ký, hỗ trợ học viên hoặc đại diện người học phù hợp. Nếu Increment ảnh hưởng tích hợp thanh toán, nên mời người hiểu nghiệp vụ thanh toán và vận hành. Nếu có thay đổi đáng kể về quyền truy cập, ý kiến chuyên môn bảo mật rất quan trọng.

Không thể thay thế toàn bộ nghiên cứu người dùng bằng một stakeholder nội bộ. Người quản lý có thể biết mục tiêu tổ chức; người học trực tiếp có thể thấy những khó khăn mà nhóm nội bộ bỏ sót. Cần phân biệt **bằng chứng từ hành vi thật**, **ý kiến của người tham gia** và **giả thuyết cần kiểm tra thêm**.

### Chủ động tạo điều kiện cho phản hồi thực chất

Nhóm có thể chia sẻ trước Product Goal, link đến môi trường có thể xem thử, quyết định đang cần ý kiến và một bản tóm tắt rất ngắn. Trong buổi Review, đặt câu hỏi cụ thể thay vì hỏi chung “Mọi người có thích không?”. Người dùng hoặc stakeholder ở xa cần có cơ hội phát biểu; không để cuộc họp chỉ xoay quanh người có chức vụ cao nhất.

## 4. Chuẩn bị Sprint Review theo hướng bằng chứng

Không cần làm một bộ slide đồ sộ. Nhưng nếu nhóm chỉ đến Review với danh sách ticket, người tham dự khó đánh giá điều gì thực sự thay đổi trong sản phẩm.

### 4.1. Nắm rõ Sprint Goal và Product Goal

**Product Goal** là mục tiêu dài hạn của Scrum Team, được thể hiện trong Product Backlog. **Sprint Goal** là mục tiêu của Sprint, được cam kết trong Sprint Backlog. Review nên có khả năng trả lời cả hai câu:

- Sprint này nhóm đã đạt hoặc tiến tới **Sprint Goal** như thế nào?
- Increment và thông tin mới đóng góp gì cho tiến triển tới **Product Goal**?

Chẳng hạn, Product Goal có thể hướng đến giúp học viên duy trì tiến độ đầu khóa, còn Sprint Goal tập trung vào việc học viên mở được bài tiếp theo từ trang khóa. Đừng biến danh sách story thành định nghĩa duy nhất của thành công: hoàn tất nhiều story không liên quan đến mục tiêu chưa chắc tạo ra kết quả đáng kể.

### 4.2. Phân biệt Done với đang làm

Một **Increment** phải đáp ứng Definition of Done của Scrum Team; các PBIs chưa đạt DoD **không trở thành một phần của Increment**. Nếu một PBI chưa đạt DoD, không nên trình bày nó như một chức năng hoàn tất hoặc phát hành được chỉ vì có bản demo chạy trên máy lập trình viên.

Nhóm vẫn có thể nói trung thực về hạng mục chưa hoàn tất, trở ngại, bất định và tác động đến hướng sản phẩm. Việc này khác với tuyên bố “đã Done” một hạng mục chưa đáp ứng chất lượng. Có thể thảo luận prototype hoặc kết quả khám phá riêng, nhưng cần gắn nhãn đúng mức sẵn sàng, tránh người xem nhầm với tính năng production.

### 4.3. Chuẩn bị bằng chứng đúng loại

| Bằng chứng | Câu hỏi hỗ trợ trả lời | Giới hạn |
| --- | --- | --- |
| **Increment hoạt động** | Khả năng mới có thực sự chạy trọn luồng không? | Chưa chứng minh người dùng cần hoặc thích |
| **Acceptance criteria và DoD** | Hành vi và mức chất lượng đã thỏa thuận có đạt không? | Chưa thay thế đo outcome |
| **Dữ liệu sự kiện sản phẩm** | Người dùng có thao tác với khả năng mới không? | Cần định nghĩa cách đo, có thể bị thiếu/trùng |
| **Phản hồi định tính** | Người dùng hiểu, khó khăn hay kỳ vọng điều gì? | Mẫu nhỏ có thể không đại diện |
| **Lỗi và quan sát vận hành** | Có vấn đề về chất lượng, tốc độ, phân quyền hoặc tích hợp không? | Không tự diễn giải nguyên nhân nhu cầu |
| **Thay đổi bối cảnh** | Có cơ hội, rủi ro, quy định hoặc phụ thuộc mới không? | Cần xác minh tác động và mức chắc chắn |

Một nhóm mới phát hành tính năng có thể **chưa có đủ thời gian quan sát outcome**. Khi đó, PO và Scrum Team nói rõ “đã bàn giao”, “đang đo” và “chưa thể kết luận”; Review vẫn có thể quyết định cần thu thập bằng chứng nào tiếp theo.

### 4.4. Chuẩn bị câu hỏi mở, không chuẩn bị kết luận sẵn

Ví dụ cho luồng “Tiếp tục học”:

- Với khóa học không có thứ tự bài cứng, “tiếp theo” nên hiểu ra sao?
- Người học có cần xem bài vừa hoàn thành hay chỉ cần mở bài mới?
- Dữ liệu trên thiết bị di động có khác máy tính không?
- Có số liệu nào cho thấy người học thực sự tiếp tục sau khi thấy nút?
- Nếu lựa chọn hiện tại chưa cải thiện kết quả, nên thử thay đổi nội dung hay cách điều hướng?

Những câu hỏi đó mời các bên **cùng ra quyết định có căn cứ**, thay vì chỉ phản hồi màu sắc và bố cục giao diện.

## 5. Một cấu trúc Sprint Review thực hành

Scrum không quy định chương trình cố định. Có thể tổ chức một Sprint Review 60–90 phút cho Sprint hai tuần **như ví dụ minh họa**, điều chỉnh theo số lượng kết quả, mức độ rủi ro và những người tham gia. Timebox chính thức vẫn phải được tôn trọng.

| Chặng | Hoạt động gợi ý | Câu hỏi dẫn dắt |
| --- | --- | --- |
| **1. Định hướng** | Nhắc Product Goal, Sprint Goal và bối cảnh hiện tại | “Chúng ta đang cố cải thiện điều gì?” |
| **2. Kết quả Sprint** | Nêu rõ PBI đạt Done, kết quả chưa hoàn tất và lý do quan trọng | “Increment nào đã sẵn sàng, phần nào chưa?” |
| **3. Kiểm tra Increment** | Quan sát luồng làm việc thật, dữ liệu hoặc môi trường phù hợp | “Khả năng mới giúp người dùng làm được gì?” |
| **4. Phản hồi và bằng chứng** | Stakeholder trao đổi tình huống, số liệu, điều kiện mới và rủi ro | “Điều gì đúng, điều gì còn sai hoặc chưa biết?” |
| **5. Quyết định hướng tiếp** | Thảo luận lựa chọn, ưu tiên và thử nghiệm sắp tới | “Nên tiếp tục, điều chỉnh, kiểm tra thêm hay dừng?” |
| **6. Kết luận** | PO làm rõ thay đổi backlog, người xác minh câu hỏi mở và khi nào xem lại | “Sau buổi này mỗi bên hiểu bước tiếp theo ra sao?” |

Thời lượng từng chặng tùy buổi. Nếu phần demo chiếm gần hết thời gian, khó có chỗ cho trao đổi về sản phẩm. Nếu phần thảo luận quá rộng sang kỹ thuật nội bộ, cần quay về kết quả cần kiểm tra; vấn đề quy trình kỹ thuật chi tiết có thể đưa vào Retrospective hoặc trao đổi chuyên môn.

### Ví dụ lời dẫn có ích

**Mở đầu:** “Product Goal hiện tại là giúp học viên học tiếp ở giai đoạn đầu khóa. Sprint Goal là giúp họ trở lại bài học phù hợp. Hôm nay nhóm sẽ xem luồng thực tế, những gì đã đạt Definition of Done, dữ liệu hiện có và ba quyết định sản phẩm còn cần ý kiến.”

**Trong demo:** “Xin một người từng xử lý tình huống này thử tìm bài tiếp theo như học viên, thay vì để nhóm luôn tự nhấn đúng đường dẫn đã thuộc.”

**Trong trao đổi:** “Nếu người học tìm nút dễ hơn nhưng chưa mở bài, có giả thuyết khác nào đáng kiểm tra? Ai có dữ liệu hoặc trải nghiệm liên quan?”

**Kết thúc:** “Chúng ta có hai lựa chọn cần làm rõ; Product Owner sẽ xem lại thứ tự backlog với nhóm. Việc thử thông báo tự động chưa được cam kết cho Sprint tiếp theo.”

## 6. Trình diễn Increment theo hành trình người dùng

Một Sprint Review thường có phần xem sản phẩm hoạt động, nhưng **không phải mọi Review đều bắt buộc có cùng kiểu demo**. Nếu có trình diễn, nên ưu tiên **luồng nghiệp vụ có ý nghĩa**, không chỉ liệt kê từng màn hình và từng API đã viết.

### Cách trình diễn kém hiệu quả

“Chúng tôi tạo ba endpoint, sửa bảng dữ liệu, thêm hai nút và đóng 14 ticket.” Người xem có thể thấy nhóm làm nhiều việc nhưng không biết học viên đã làm được điều gì và kết quả có tốt hơn không.

### Cách trình diễn gắn với mục tiêu

“Một học viên đã hoàn tất bài đầu đăng nhập lại, mở trang khóa, thấy hành động tiếp tục và truy cập đúng bài kế tiếp. Khi quyền học hết hiệu lực, hệ thống không cho mở liên kết trực tiếp; nếu đã hoàn thành bài cuối, học viên thấy trạng thái phù hợp.”

Nhóm có thể sử dụng tài khoản và dữ liệu thử đã được chuẩn bị để không làm lộ thông tin cá nhân. Nếu trình diễn qua hệ thống staging, cần nói rõ nó khác môi trường production ở đâu. Không dùng dữ liệu nhạy cảm thật để minh họa chỉ vì sẽ thuận tiện hơn.

### Ví dụ tiêu chí hành vi của Increment

~~~gherkin
Feature: Tiếp tục học từ trang khóa

  Scenario: Học viên có quyền học và có bài tiếp theo
    Given học viên đã đăng nhập và có quyền truy cập khóa
    And bài đầu đã được ghi nhận hoàn tất
    When học viên mở trang chi tiết khóa
    Then hệ thống hiển thị hành động "Tiếp tục học"
    And hành động mở bài tiếp theo hợp lệ

  Scenario: Học viên đã hoàn thành bài cuối
    Given học viên có quyền học và đã hoàn thành bài cuối
    When học viên mở trang chi tiết khóa
    Then hệ thống cho biết khóa đã hoàn thành
    And không dẫn đến bài học không tồn tại

  Scenario: Người không có quyền thử mở liên kết trực tiếp
    Given người dùng không có quyền học khóa
    When người dùng yêu cầu truy cập bài bị hạn chế
    Then hệ thống từ chối truy cập nội dung đó
~~~

Các tiêu chí này là minh họa theo quy tắc giả định; trong hệ thống thật, Product Owner và người hiểu nghiệp vụ cần xác nhận ý nghĩa “bài tiếp theo”, “hoàn thành” và “có quyền học”.

### Demo không thay thế kiểm thử

Việc một luồng chạy thành công trước stakeholder không chứng minh tất cả trường hợp biên, hiệu năng hay bảo mật đều đúng. Definition of Done phải được đáp ứng **trước khi coi PBI là Done**. Review không phải nơi dùng sự đồng ý của stakeholder để bỏ qua test hoặc rút bớt yêu cầu chất lượng.

## 7. Ví dụ xuyên suốt: Sprint Review của sản phẩm học trực tuyến

### 7.1. Mục tiêu và kết quả Sprint

Giả sử Scrum Team đặt:

- **Product Goal:** giúp học viên mới duy trì tiến độ trong giai đoạn đầu khóa, với trải nghiệm học đáng tin cậy.
- **Sprint Goal:** cho học viên đã ghi danh khả năng tìm và mở đúng bài tiếp theo từ trang khóa.
- **Increment đã Done:** nút “Tiếp tục học”, kiểm tra quyền truy cập, xử lý trạng thái đã hoàn thành khóa và kiểm thử hồi quy cần thiết.

Một hạng mục khác là “gửi nhắc học tự động” mới triển khai một phần và **chưa đạt Definition of Done**. Nhóm công khai điều này, không đưa nó vào danh sách Increment hoàn thành và không trình bày nó như chức năng đã được chấp nhận.

### 7.2. Các stakeholder đem đến những thông tin gì?

| Stakeholder | Phản hồi hoặc quan sát | Câu hỏi mà nhóm nên xem xét |
| --- | --- | --- |
| Đại diện học viên | Dễ tìm hành động tiếp tục hơn, nhưng tên bài không cho biết nội dung học sắp tới | Có cần thêm ngữ cảnh trước khi người học quyết định mở bài không? |
| Giảng viên | Một số khóa cho phép học không theo thứ tự, nên “bài kế tiếp” chưa luôn rõ | Có cần phân biệt đường học tuyến tính và tự chọn không? |
| Hỗ trợ | Một nhóm người học vẫn hỏi vì sao tiến độ không giống giữa điện thoại và máy tính | Có vấn đề đồng bộ dữ liệu cần điều tra trước khi mở rộng không? |
| Developers | Dữ liệu khóa tuyến tính ổn định, nhưng khóa tự chọn có nhiều trường hợp biên | Nên chia biến thể theo loại khóa để giao giá trị an toàn không? |
| Product Owner | Mục tiêu là học viên thực sự quay lại học, không chỉ thấy nút mới | Bằng chứng sử dụng nào đủ để tiếp tục hoặc đổi hướng? |

Không phản hồi nào tự động quyết định toàn bộ roadmap. PO cùng nhóm xem tần suất, mức ảnh hưởng, rủi ro và khả năng kiểm tra các giả thuyết trước khi sắp xếp lại Product Backlog.

### 7.3. Phân biệt kết quả đã biết với điều chưa rõ

Giả sử trước buổi Review có một tập số liệu minh họa:

| Nhóm sử dụng | Học viên đủ điều kiện | Học viên mở bài tiếp theo trong 7 ngày | Tỷ lệ |
| --- | ---: | ---: | ---: |
| A – trải nghiệm cũ | 250 | 80 | 32% |
| B – trải nghiệm mới | 250 | 97 | 38,8% |

Chênh lệch quan sát là **6,8 điểm phần trăm**, mức tăng tương đối khoảng **21,25%** so với nhóm A. Đây là **số liệu giả định phục vụ bài học**, không phải kết quả của thử nghiệm thật. Cách tính cũng không tự chứng minh trải nghiệm mới gây ra cải thiện.

Để diễn giải đáng tin, nhóm cần biết cách phân nhóm, định nghĩa “đủ điều kiện”, cách đo “mở bài”, thời gian theo dõi, dữ liệu thiếu/trùng và độ bất định. Nếu các điều kiện chưa rõ, Scrum Team nên nói **“đây là tín hiệu ban đầu”**, không khẳng định “đã tăng chắc chắn 21,25% nhờ nút mới”.

### 7.4. Những quyết định tiếp theo có thể xuất hiện

Sau thảo luận, PO và Scrum Team có thể:

1. Ưu tiên kiểm tra và xử lý vấn đề đồng bộ tiến độ nếu nguy cơ mất dữ liệu đáng kể.
2. Chia yêu cầu “Tiếp tục học” thành biến thể cho **khóa tuyến tính** và **khóa tự chọn**, dựa trên chính sách nghiệp vụ.
3. Tiếp tục quan sát tỷ lệ mở bài và tỷ lệ **hoàn thành nội dung**, không chỉ số nhấn nút.
4. Hoãn tự động gửi nhắc học cho đến khi có bằng chứng người học cần và chấp thuận kênh thông báo.
5. Tìm hiểu xem độ dài bài học hoặc nội dung có phải rào cản tiếp theo không.

Những lựa chọn trên là **ứng viên** cho Product Backlog, không phải danh sách bắt buộc phải thực hiện toàn bộ. PO chịu trách nhiệm về thứ tự Product Backlog; Scrum Team sẽ xem khả năng và Sprint Goal thích hợp khi bước sang Sprint Planning.

~~~mermaid
flowchart TD
    A["Increment: Tiếp tục học với kiểm tra quyền"] --> B["Review cùng stakeholder"]
    B --> C["Tín hiệu: người học tìm bài dễ hơn"]
    B --> D["Vấn đề mới: tiến độ đa thiết bị"]
    B --> E["Biến thể: khóa học tự chọn"]
    C --> F["Tiếp tục đo outcome thật"]
    D --> G["Đánh giá rủi ro và ưu tiên sửa nếu cần"]
    E --> H["Làm rõ quy tắc, chia story"]
    F --> I["Product Owner xem lại thứ tự backlog"]
    G --> I
    H --> I
    I --> J["Lựa chọn cho các Sprint tương lai"]
~~~

### 7.5. Review thành công được nhận biết bằng gì?

Một Sprint Review hữu ích không cần chứng minh rằng mọi giả thuyết đều đúng. Nó thành công khi người tham gia có **cùng hiểu biết về kết quả**, dám nói rõ **điều chưa biết**, đưa ra **những quyết định ưu tiên có thể giải thích** và biết cần quan sát hoặc thử nghiệm gì tiếp theo.

## 8. Đo tiến triển tới Product Goal, không chỉ đếm ticket

Sprint Review nên kết hợp **Increment** với **kết quả người dùng**, **chất lượng** và **thông tin bối cảnh**. Các chỉ số chỉ giúp ích nếu cách đo nhất quán, nguồn dữ liệu đáng tin và được diễn giải theo đúng phạm vi.

| Loại tín hiệu | Ví dụ với nền tảng học | Cách dùng phù hợp |
| --- | --- | --- |
| **Tiến triển Sprint Goal** | Học viên có thể mở đúng bài tiếp theo qua luồng hoàn chỉnh | Xem Increment có hỗ trợ mục tiêu Sprint không |
| **Outcome người dùng** | Tỷ lệ học viên quay lại mở bài tiếp theo trong bảy ngày | Xác định thay đổi hành vi cần kiểm chứng |
| **Giá trị lâu dài** | Tỷ lệ hoàn thành khóa hoặc tiến bộ học tập có ý nghĩa | Kiểm tra tác động bền vững, không chỉ tương tác ngắn |
| **Trải nghiệm định tính** | Học viên có hiểu đường học và trạng thái hiện tại không? | Phát hiện vấn đề chưa hiện rõ trong số liệu |
| **Guardrail chất lượng** | Lỗi phân quyền, mất tiến độ, thời gian tải, lỗi sau phát hành | Không tối ưu một chỉ số bằng cách gây thiệt hại khác |
| **Thông tin bối cảnh** | Nội dung khóa thay đổi, chính sách ghi danh mới | Xem lại giả thuyết và thứ tự backlog |

### Đặt chỉ số đúng mẫu số

Ví dụ minh họa:

~~~text
Tỷ lệ mở bài tiếp theo trong 7 ngày
  = Số học viên duy nhất đủ điều kiện đã hoàn thành bài 1
      và mở bài 2 trong vòng 7 ngày
    / Số học viên duy nhất đủ điều kiện đã hoàn thành bài 1
~~~

Phải kiểm tra điều kiện hợp lệ: khóa có bài thứ hai không, người học có quyền truy cập không, sự kiện trên hai thiết bị có bị tính trùng không, có nhóm người học nào được loại ra vì quy tắc nghiệp vụ không. Nếu chưa biết chính xác, cần ghi giới hạn thay vì gán ý nghĩa chắc chắn cho tỷ lệ.

### Khi chưa có đủ dữ liệu outcome

Một tính năng vừa được phát hành có thể chưa có đủ người dùng để rút kết luận. Nhóm có thể:

- Kiểm tra phần mềm hoạt động và các guardrail kỹ thuật trước.
- Xác định công cụ thu thập sự kiện và cách kiểm tra chất lượng dữ liệu.
- Lên kế hoạch quan sát một số phiên sử dụng hoặc phỏng vấn người dùng phù hợp.
- Chốt mốc xem lại khi dữ liệu đã có phạm vi quan sát đủ hữu ích.
- Tiếp tục ưu tiên việc khác nếu chi phí chờ hoặc rủi ro không cho phép dừng toàn bộ phát triển.

Không nên chạy thử nghiệm có đối chứng rồi liên tục dừng đúng lúc một nhóm đang thắng mà không có quy tắc phân tích phù hợp. Dữ liệu định tính và định lượng hỗ trợ những câu hỏi khác nhau; không có một chỉ số duy nhất chứng minh mọi khía cạnh giá trị.

### Số liệu luồng công việc có vai trò gì?

Các chỉ số Kanban như **WIP**, **cycle time**, **throughput** và **work item age** có thể cho thấy việc bàn giao đang chậm hoặc hạng mục bị chặn. Chúng giúp nhóm ra quyết định về năng lực giao sản phẩm, nhưng **không trực tiếp đo Product Goal**. Có thể mang xu hướng quan trọng vào Sprint Review nếu nó ảnh hưởng thời điểm thu thập giá trị; phần đào sâu cách phối hợp nội bộ thích hợp hơn với Retrospective.

## 9. Từ phản hồi trong Review đến Product Backlog thích ứng

Điểm kết nối quan trọng nhất của Sprint Review là **quyết định về sản phẩm sau khi kiểm tra**. Một phản hồi có thể dẫn đến:

- **Làm rõ PBI:** bổ sung quy tắc nghiệp vụ hoặc tiêu chí chấp nhận.
- **Chia nhỏ story/epic:** tách biến thể để giao một lát có giá trị sớm hơn.
- **Sắp xếp lại ưu tiên:** đưa vấn đề gây rủi ro hoặc giá trị lớn lên trước.
- **Tạo PBI khám phá:** nghiên cứu giả thuyết chưa có bằng chứng, làm prototype hoặc spike kỹ thuật có timebox.
- **Loại bỏ hoặc hoãn ý tưởng:** khi lợi ích thấp hoặc bằng chứng không ủng hộ.
- **Xem lại Product Goal:** khi có thay đổi đáng kể khiến mục tiêu hiện tại không còn phù hợp; cần quyết định minh bạch, không đổi tùy tiện.

### Mẫu biến quan sát thành quyết định

| Quan sát tại Review | Câu hỏi bổ sung | Hành động backlog có thể cân nhắc |
| --- | --- | --- |
| Người dùng dễ tìm nút nhưng không mở bài | Có trở ngại nội dung, thời gian hay động lực? | Thêm hoạt động khám phá thay vì xây ngay tính năng lớn |
| Luồng hoạt động tốt cho khóa tuyến tính, chưa hỗ trợ khóa tự chọn | Bao nhiêu người học theo hình thức tự chọn? Quy tắc chọn bài là gì? | Tạo story biến thể có tiêu chí chấp nhận rõ |
| Có lỗi mất tiến độ trên hai thiết bị | Tác động dữ liệu và số người bị ảnh hưởng thế nào? | Triage bug và ưu tiên theo mức rủi ro |
| Stakeholder yêu cầu gửi email nhắc học hằng ngày | Người dùng có mong muốn và đồng ý nhận email không? | Thử khảo sát/opt-in có kiểm soát trước |
| Chưa có dữ liệu về tỷ lệ quay lại | Có thu thập sự kiện đúng chưa? | Làm rõ cách đo và tạo nhiệm vụ quan sát cần thiết |

**Product Backlog không phải danh sách yêu cầu được bỏ phiếu theo số đông.** PO là người chịu trách nhiệm về việc sắp xếp thứ tự, sử dụng phản hồi của stakeholder, thông tin kỹ thuật và Product Goal để đưa ra quyết định. Developers góp ý độ phức tạp, phụ thuộc và các lựa chọn chia lát; họ không bị buộc nhận toàn bộ việc vừa nêu tại Review.

### Phản hồi không đồng nghĩa giao việc lập tức

Trong Review, một stakeholder có thể nêu “Cần thêm biểu đồ tiến độ”. Nên ghi:

> “Người dùng nào cần biểu đồ để quyết định điều gì? Có bằng chứng họ không làm được việc đó với dữ liệu hiện có không? Có cách đơn giản hơn để kiểm chứng giá trị không?”

Từ đó mới xác định nên tạo story, nghiên cứu, thử một lát hoặc chưa làm. Nhu cầu mới có thể rất đáng giá, nhưng thứ tự cần được cân đối với Product Goal và các rủi ro đang có.

## 10. Sprint Review khác các hoạt động dễ bị nhầm lẫn

| Hoạt động | Mục đích chính | Không nên nhầm với |
| --- | --- | --- |
| **Sprint Planning** | Scrum Team xác định Sprint Goal, công việc và kế hoạch cho Sprint sắp tới | Review không phải nơi buộc chốt Sprint Backlog tiếp theo |
| **Daily Scrum** | Developers kiểm tra tiến độ tới Sprint Goal và điều chỉnh kế hoạch | Review không phải buổi báo cáo từng cá nhân |
| **Sprint Review** | Cùng stakeholder kiểm tra kết quả Sprint và thích ứng hướng sản phẩm | Không chỉ là demo hoặc lễ nghiệm thu |
| **Sprint Retrospective** | Scrum Team xem chất lượng/hiệu quả cách làm và lên cải tiến | Review tập trung kết quả sản phẩm, bối cảnh và hướng tiếp theo |
| **User acceptance testing (UAT)** | Kiểm tra hệ thống đáp ứng tiêu chí chấp nhận trong phạm vi đã định, tùy tổ chức | UAT không tự thay thế Review và không cho phép bỏ qua DoD |
| **Release/deployment** | Đưa Increment phù hợp đến môi trường/người dùng mục tiêu | Không bắt buộc đợi Review mới được release nếu đáp ứng điều kiện cần thiết |
| **Demo nội bộ** | Cho thấy một luồng hoặc phát hiện cụ thể | Chưa chắc có stakeholder, Product Goal hoặc quyết định thích ứng |

### Sprint Review khác Sprint Retrospective thế nào?

**Sprint Review hỏi:** “Sản phẩm và môi trường đã thay đổi thế nào? Chúng ta nên làm gì tiếp để tạo giá trị?”

**Sprint Retrospective hỏi:** “Cách phối hợp, công cụ và chất lượng thực hiện cần cải thiện thế nào để hiệu quả hơn?”

Hai sự kiện liên quan nhưng không trùng nhau. Ví dụ, trong Review, stakeholder nhận ra học viên không hiểu tên trạng thái “Đang học”; Product Backlog có thể ưu tiên sửa trải nghiệm. Trong Retrospective, Scrum Team xem vì sao tiêu chí chấp nhận về ngôn ngữ chưa được làm rõ sớm và đề xuất mời người hỗ trợ vào refinement.

### Review không phải cổng phê duyệt phát hành

Theo Scrum, Increment phải **đạt Definition of Done để được xem là hoàn tất**. Increment có thể được cung cấp cho stakeholder **trước khi Sprint kết thúc**, và Sprint Review **không được xem là cổng để phát hành giá trị**. Nhóm có thể release thường xuyên theo năng lực và ràng buộc của tổ chức, sau đó dùng Review để kiểm tra kết quả và lựa chọn tiếp theo.

Nếu tổ chức có yêu cầu phê duyệt pháp lý, an toàn hoặc thương mại trước một số lần phát hành, các kiểm soát ấy vẫn cần được tuân thủ; nhưng chúng là **quy trình/ràng buộc riêng**, không phải mục đích cốt lõi của Sprint Review.

## 11. Xử lý hạng mục chưa Done, lỗi và thay đổi ngoài kế hoạch

Một Sprint không nhất thiết hoàn tất mọi PBI từng được dự kiến. Review cần thể hiện **thực tế**:

1. PBI nào đã đạt DoD và góp phần tạo Increment.
2. PBI nào chưa Done, những trở ngại hoặc bất định quan trọng là gì.
3. Sprint Goal đạt đến đâu và phần chưa đạt ảnh hưởng mục tiêu thế nào.
4. Những thay đổi về người dùng, thị trường, kỹ thuật hoặc ràng buộc đã xảy ra.
5. Lựa chọn phù hợp cho Product Backlog và các Sprint tương lai.

### Không “chấp nhận tạm” chất lượng thấp để có nhiều điểm Done

Nếu story được mô tả “người học không được xem nội dung khóa khi không có quyền” nhưng kiểm thử cho thấy liên kết trực tiếp bỏ qua phân quyền, story đó **chưa đạt DoD**. Không thể nhờ stakeholder bấm “Accept” tại Review để biến nó thành Increment hợp lệ. Nhóm cần đánh giá rủi ro và khắc phục trước khi coi công việc hoàn tất.

### Không biến một trở ngại thành buổi chỉ trích

Nếu một tích hợp chưa hoàn thành vì thiếu tài khoản kiểm thử, nhóm có thể nêu tác động và bước xử lý. Review không phải tòa án tìm người chịu lỗi hay nơi ép mỗi cá nhân giải thích “tại sao chậm”. Các nguyên nhân về cách làm, hệ thống và phối hợp có thể tiếp tục được phân tích trong Sprint Retrospective.

### Một số tình huống cần hành động trước Review

Lỗi bảo mật nghiêm trọng, mất dữ liệu hoặc dịch vụ production ngừng hoạt động cần được xử lý theo mức khẩn và quy trình sự cố; nhóm không phải đợi Sprint Review mới báo hoặc khắc phục. Khi Review diễn ra, có thể chia sẻ những thay đổi đó ảnh hưởng hướng sản phẩm như thế nào, đồng thời bảo vệ thông tin nhạy cảm.

## 12. Sprint Review hiệu quả khi làm việc từ xa hoặc nhóm phân tán

Một Sprint Review từ xa có thể vẫn rất thực chất nếu mọi người nhìn thấy cùng Increment, có cơ hội thử, nói rõ bằng chứng và quyết định. Một số cách hỗ trợ:

- **Chia sẻ mục tiêu và tài liệu ngắn trước buổi họp:** Product Goal, Sprint Goal, link demo an toàn và các câu hỏi cần quyết định.
- **Ưu tiên demo trực tiếp khi phù hợp:** cho người tham gia thực hiện tác vụ với dữ liệu giả lập, thay vì chỉ trình chiếu ảnh chụp.
- **Có phương án dự phòng:** nếu môi trường demo gặp lỗi mạng, mô tả trung thực tình trạng và dùng bằng chứng kiểm thử/ghi hình phù hợp; không gọi một đoạn video là bằng chứng đầy đủ của production.
- **Ghi phản hồi ngay tại chỗ:** phân biệt sự kiện quan sát, câu hỏi, giả thuyết và yêu cầu giải pháp.
- **Mời người ít nói tham gia:** hỏi theo vai trò hoặc tình huống, cho phép góp ý viết nếu điều kiện âm thanh/múi giờ hạn chế.
- **Kết thúc với quyết định minh bạch:** ai cần xác minh điều gì, PO sẽ điều chỉnh Product Backlog ra sao và khi nào kiểm tra lại.

Không nên biến Review thành trình tự mở hàng chục slide và đọc từng ticket. Mục tiêu là tạo **cuộc trao đổi có chất lượng về sản phẩm**, không phải trình diễn kỹ năng thuyết trình.

### Ghi kết luận ngắn gọn

Một bản ghi Review có thể đơn giản:

~~~text
Product Goal: <mục tiêu dài hạn>
Sprint Goal: <mục tiêu của Sprint đã kết thúc>
Increment đạt DoD: <những khả năng thực sự hoàn tất>
Chưa Done/giới hạn: <phạm vi còn lại, trở ngại quan trọng>
Bằng chứng/feedback: <nguồn, mẫu, thời gian, độ tin cậy>
Thay đổi bối cảnh: <thị trường, chính sách, kỹ thuật, người dùng>
Các lựa chọn được thảo luận: <tiếp tục / điều chỉnh / nghiên cứu / dừng>
Điều chỉnh Product Backlog: <quyết định hoặc mục cần PO làm rõ>
Câu hỏi mở: <ai xác minh, khi nào>
Mốc kiểm tra kết quả tiếp theo: <sự kiện hoặc thời gian có bằng chứng>
~~~

Đây chỉ là mẫu hỗ trợ minh bạch, **không phải artifact bắt buộc mới của Scrum**. Đừng biến việc ghi biên bản thành một bước phê duyệt phức tạp khiến quyết định đến muộn.

## 13. Kết nối Sprint Review với Kanban, XP và đo lường luồng

Trong phạm vi Agile Development, Scrum cung cấp Sprint Review làm nhịp kiểm tra và thích ứng hướng sản phẩm; những kỹ thuật từ các cách tiếp cận khác có thể giúp Scrum Team tạo bằng chứng tốt hơn.

### Kanban: thấy dòng giá trị bị tắc ở đâu

Nhóm có thể trực quan hóa công việc, giới hạn WIP và quan sát throughput, cycle time, work item age. Ví dụ, nếu nhiều story chưa đến Done vì đợi review code, nhóm có ít Increment để mang tới Sprint Review. Đó là tín hiệu quan trọng về **khả năng bàn giao tăng dần**, nhưng buổi phân tích sâu cách điều phối review code nên được thực hiện trong Retrospective hoặc buổi xử lý quy trình thích hợp.

### XP: chất lượng kỹ thuật làm phản hồi đáng tin hơn

Kiểm thử tự động, tích hợp liên tục, refactoring và các hình thức cộng tác kỹ thuật của XP giúp giảm lỗi tích hợp. Khi Increment đạt DoD thường xuyên, Sprint Review có thể tập trung vào **giá trị và hành vi người dùng** thay vì dành toàn bộ thời gian chữa lỗi demo. Nếu phát hiện nhu cầu mới, năng lực kỹ thuật tốt giúp nhóm thay đổi an toàn ở Sprint sau.

### User story và backlog là cầu nối đến quyết định

Một user story nên nêu người hưởng lợi, kết quả và tiêu chí chấp nhận. Tại Review, nhóm dùng kết quả thực tế để kiểm tra giả định đó. Nếu khách hàng chưa nhận được lợi ích, có thể điều chỉnh story, chia epic, tạo spike kiểm chứng hoặc bỏ hẳn một phương án. Product Backlog là danh sách **có thể thích ứng**, không phải hợp đồng xây tất cả ý tưởng đã từng ghi.

## 14. Những phản mẫu của Sprint Review

| Phản mẫu | Hệ quả | Cách cải thiện |
| --- | --- | --- |
| **Chỉ trình diễn slide hoặc đọc ticket Done** | Stakeholder không kiểm tra được hành trình và giá trị | Cho thấy Increment hoạt động, liên kết với mục tiêu và bằng chứng |
| **Biến Review thành buổi phê duyệt trước release** | Giá trị đến muộn; nhầm vai trò DoD | Tách chất lượng/release khỏi mục đích kiểm tra và thích ứng |
| **Không mời stakeholder có thông tin thực chất** | Review thành buổi nói chuyện nội bộ, khó phát hiện vấn đề | Mời người am hiểu người dùng, nghiệp vụ và ràng buộc liên quan |
| **Chỉ hỏi “mọi người có thích không?”** | Phản hồi thiên về cảm giác, ít hành động | Hỏi theo tác vụ, tình huống và giả thuyết cần kiểm tra |
| **Tất cả phản hồi đều trở thành cam kết Sprint sau** | Backlog phình, mất quyền ưu tiên và tập trung | PO cân nhắc giá trị, rủi ro, mức hiểu biết và Product Goal |
| **Che giấu story chưa đạt DoD** | Người tham gia tưởng sản phẩm đã sẵn sàng | Nêu rõ Done/chưa Done, giữ tiêu chuẩn chất lượng |
| **Chỉ báo velocity hoặc số ticket** | Không biết hành vi người dùng có cải thiện | Kết hợp outcome, guardrail và bằng chứng định tính |
| **Không điều chỉnh hướng đi dù bằng chứng mới trái giả thuyết** | Review mang tính nghi lễ, mất năng lực thích ứng | Ghi lựa chọn và điều chỉnh Product Backlog có căn cứ |
| **Biến Review thành Retrospective** | Stakeholder phải nghe tranh luận nội bộ; ít thời gian cho sản phẩm | Tách quyết định sản phẩm và cải tiến cách làm |
| **Tranh cãi người nào “làm chậm Sprint”** | Thành viên che giấu rủi ro, giảm tin tưởng | Tập trung sự kiện, tác động, bước tiếp theo; xem quy trình trong Retro |
| **Kết luận chỉ từ mẫu dữ liệu nhỏ** | Dễ chọn sai hướng đầu tư | Ghi giới hạn bằng chứng, kiểm tra thêm khi cần |
| **Mọi quyết định đã được chốt trước buổi họp** | Stakeholder không thực sự tham gia kiểm tra/adaptation | Chuẩn bị câu hỏi mở và sẵn sàng đổi ý khi có bằng chứng |

Một Review hiệu quả không cần luôn diễn ra suôn sẻ hoặc nhận được toàn lời khen. **Phát hiện sớm rằng giả thuyết sai có thể là kết quả rất có giá trị**, vì giúp nhóm tránh đầu tư tiếp vào hướng không còn hợp lý.

## 15. Bài thực hành: điều phối Sprint Review cho sản phẩm đăng ký khóa học

### 15.1. Tình huống

Scrum Team phát triển một nền tảng học lập trình. Product Goal là giúp học viên mới có thể tìm khóa, ghi danh và bắt đầu học thuận lợi. Sprint Goal hiện tại:

> “Cho học viên đã đăng nhập ghi danh một khóa miễn phí đang mở và truy cập được bài đầu với trạng thái chính xác.”

Kết thúc Sprint, nhóm có:

1. Increment **đạt DoD** cho luồng ghi danh khóa miễn phí và kiểm tra không tạo đăng ký trùng.
2. Một trang thống kê quản trị còn thiếu phân quyền và kiểm thử, **chưa đạt DoD**.
3. Một số học viên thử báo họ không hiểu khác biệt giữa “Đã ghi danh” và “Đang chờ duyệt”.
4. Bộ phận vận hành cho biết một số khóa bắt đầu áp dụng điều kiện tiên quyết.
5. Stakeholder kinh doanh muốn thêm thanh toán khóa trả phí ngay trong Sprint tới.
6. Dữ liệu sử dụng thật của Increment mới chưa đủ để kết luận tỷ lệ bắt đầu học thay đổi.

### 15.2. Nhiệm vụ cho người học

1. Xác định **mục đích của Sprint Review** này; những câu hỏi nào cần cả Scrum Team và stakeholder trao đổi?
2. Lập **chương trình Review ngắn**, làm rõ điều gì sẽ được trình diễn và bằng chứng nào còn thiếu.
3. Phân loại từng thông tin (1)–(6): kết quả Done, việc chưa Done, phản hồi người dùng, thay đổi bối cảnh hay đề xuất mới.
4. Viết **ba câu hỏi mở** để hiểu vấn đề “Đã ghi danh” và “Đang chờ duyệt” mà không áp ngay giải pháp UI.
5. Đề xuất **hai hoặc ba lựa chọn thích ứng Product Backlog**, nêu giá trị/rủi ro/điều cần xác minh.
6. Giải thích vì sao yêu cầu thanh toán mới **không tự động là cam kết Sprint sau**.
7. Chọn **một outcome và hai guardrail** để kiểm tra khi đủ dữ liệu.
8. Nêu một vấn đề nên đưa sang **Sprint Retrospective** thay vì giải quyết chi tiết trong Review.

### 15.3. Một lời giải tham khảo

**Mục đích:** cùng kiểm tra Increment ghi danh đã hoàn thành, tiến triển tới Product Goal, phản hồi về trạng thái đăng ký và tác động của điều kiện tiên quyết; quyết định công việc nào đáng ưu tiên tiếp.

**Chương trình gợi ý:** bắt đầu bằng mục tiêu; trình diễn học viên đủ điều kiện ghi danh và mở bài đầu, cùng tình huống gửi yêu cầu lặp; nói rõ trang quản trị chưa đạt DoD; mời stakeholder trao đổi về “chờ duyệt” và điều kiện tiên quyết; xác định những bằng chứng cần thu thập; kết thúc bằng định hướng ưu tiên do PO làm rõ.

**Ba câu hỏi mở:**

- Với những khóa nào “chờ duyệt” là trạng thái nghiệp vụ hợp lệ, và ai quyết định duyệt?
- Học viên nhìn thấy gì ở từng trạng thái, họ muốn làm gì tiếp và thông tin nào gây hiểu nhầm?
- Điều kiện tiên quyết áp dụng theo khóa hay từng nhóm học viên, dữ liệu nào xác nhận đã đạt điều kiện?

**Lựa chọn backlog:** (a) làm rõ và chuẩn hóa cách hiển thị trạng thái theo quy tắc được xác nhận; (b) thêm kiểm tra điều kiện tiên quyết trước khi ghi danh vào những khóa có quy định; (c) xem xét thanh toán trả phí sau khi khám phá yêu cầu nghiệp vụ và rủi ro tích hợp. Thứ tự phải dựa trên tác động thực tế, mức khẩn cấp, Product Goal và thông tin từ Developers.

**Không cam kết ngay thanh toán:** Product Owner chịu trách nhiệm thứ tự Product Backlog; Sprint Goal và phạm vi cho Sprint sau chỉ được xác định thông qua Sprint Planning cùng Scrum Team và năng lực thực tế. Một yêu cầu mới có thể rất quan trọng nhưng cần làm rõ giá trị, phụ thuộc và mức sẵn sàng.

**Outcome:** tỷ lệ học viên đủ điều kiện đã ghi danh hợp lệ mở được bài đầu trong khoảng thời gian được thống nhất. **Guardrail:** không có cấp quyền học sai; không tăng lỗi tạo đăng ký trùng hoặc sai trạng thái. Khi dữ liệu ít, cần nói rõ giới hạn kết luận.

**Đưa sang Retrospective:** phân tích vì sao trang quản trị bị thiếu kiểm thử phân quyền và cách cải thiện hoạt động refinement/DoD, thay vì dùng toàn bộ Review để tìm người chịu trách nhiệm lỗi đó.

Không có một thứ tự backlog duy nhất đúng cho mọi sản phẩm. Điểm quan trọng là **cùng nhìn vào thực tế, phân biệt bằng chứng với giả thuyết, giữ chất lượng và có lựa chọn tiếp theo rõ ràng**.

## 16. Checklist để Sprint Review tạo ra thích ứng thực chất

- [ ] Scrum Team và stakeholder có hiểu **Product Goal và Sprint Goal** trước khi kiểm tra kết quả?
- [ ] Những người tham gia có **bối cảnh hoặc khả năng cung cấp phản hồi quan trọng**?
- [ ] Increment được trình bày đúng mức sẵn sàng, chỉ gọi **Done** những PBIs đạt Definition of Done?
- [ ] Buổi Review dùng **hành trình người dùng và kết quả thật**, không chỉ danh sách task đã hoàn tất?
- [ ] Điều chưa hoàn thành, giả thuyết, rủi ro và giới hạn dữ liệu được nêu minh bạch?
- [ ] Stakeholder được mời **hỏi, quan sát, thử và phản biện** trong không khí xây dựng?
- [ ] Nhóm đã kiểm tra **tiến triển tới Product Goal**, không chỉ so Sprint với kế hoạch ticket?
- [ ] Có thảo luận **thay đổi bối cảnh**: nhu cầu, thị trường, pháp lý, công nghệ, vận hành?
- [ ] Các chỉ số outcome, chất lượng và guardrail có **định nghĩa và nguồn đo đáng tin cậy**?
- [ ] Phản hồi được phân biệt thành **quan sát, giả thuyết, câu hỏi và đề xuất giải pháp**?
- [ ] Product Owner có thông tin để **điều chỉnh Product Backlog và thứ tự ưu tiên**?
- [ ] Ý tưởng mới không bị hiểu nhầm thành **cam kết tự động cho Sprint tiếp theo**?
- [ ] Buổi Review không biến thành **cổng release**, **buổi báo cáo cá nhân** hoặc **Retrospective**?
- [ ] Những câu hỏi chưa rõ có người phối hợp, bước xác minh và thời điểm xem lại?
- [ ] Cả nhóm biết **tiếp tục, điều chỉnh, thử nghiệm thêm hay dừng** phương án nào sau Review?

**Ghi nhớ:** Sprint Review là cơ hội để Scrum Team và stakeholder **cùng kiểm tra kết quả Sprint, học từ Increment và bối cảnh thực tế, rồi xác định hướng thích ứng tiếp theo**. Một buổi Review tốt không chỉ cho thấy sản phẩm đã làm được gì mà còn làm rõ **nó tạo ra giá trị nào, điều gì chưa được xác nhận và Product Backlog nên thay đổi ra sao**. Nhờ vậy, Scrum hỗ trợ Agile phát triển bằng phản hồi sớm, bàn giao tăng dần và cải tiến liên tục thay vì chỉ hoàn tất danh sách tính năng.
