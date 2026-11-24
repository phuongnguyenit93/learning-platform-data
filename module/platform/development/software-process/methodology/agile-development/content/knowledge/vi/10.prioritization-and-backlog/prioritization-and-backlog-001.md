# Vai trò của danh sách công việc tồn đọng trong phát triển thích ứng

Một nhóm phát triển phần mềm thường có nhiều việc hơn khả năng thực hiện: yêu cầu từ người dùng, lỗi cần sửa, giả định phải kiểm chứng, hạ tầng cần cải tiến, rủi ro bảo mật và những ý tưởng mới phát sinh. Nếu tất cả cùng được xem là “việc phải làm ngay”, nhóm sẽ phân tán nguồn lực; nếu danh sách bị đóng băng từ đầu dự án, nhóm sẽ tiếp tục thực hiện những lựa chọn đã lỗi thời dù hiểu biết về người dùng đã thay đổi.

Trong **Agile**, danh sách công việc tồn đọng (*backlog*) là một công cụ để **làm rõ các lựa chọn còn mở, tạo sự minh bạch về ưu tiên và hỗ trợ ra quyết định thích ứng**. Backlog có ích khi giúp nhóm trả lời thường xuyên: *Mục tiêu hiện tại là gì? Việc tiếp theo nào đem lại giá trị hoặc giảm rủi ro lớn nhất? Điều gì mới được học khiến thứ tự công việc cần đổi?*

Bài học thuộc chương **Ưu tiên và backlog** của module **AGILE_DEVELOPMENT**. Nội dung kết nối giá trị Agile về phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục với user story, Product Backlog trong Scrum, quản lý dòng công việc bằng Kanban, năng lực thay đổi an toàn của XP và cách đo lường tiến độ theo bằng chứng.

## 1. Vì sao phát triển thích ứng cần một backlog?

Giả sử một nền tảng học tập đang xây chức năng **đăng ký workshop**. Ban đầu, bên liên quan muốn lịch tháng, bộ lọc, email xác nhận và màn hình quản trị. Sau khi thử với người dùng, nhóm phát hiện ba điều:

1. Học viên chủ yếu thao tác bằng điện thoại và thích danh sách các khung giờ còn chỗ hơn lịch tháng.
2. Học viên lo lắng nhất về việc hệ thống thông báo “đã đăng ký” nhưng thực tế không giữ được chỗ.
3. Nhân viên hỗ trợ tốn nhiều thời gian giải quyết yêu cầu hủy và chuyển chỗ.

Nếu kế hoạch ban đầu được coi là danh sách chức năng bắt buộc phải hoàn thành theo đúng thứ tự, cả nhóm có thể tiếp tục đầu tư vào lịch tháng và bộ lọc nâng cao trong khi chưa xử lý vấn đề quan trọng. Backlog được quản lý thích ứng cho phép **giữ mục tiêu kinh doanh**, nhưng **đổi thứ tự hoặc thay thế giải pháp** khi bằng chứng mới xuất hiện.

Backlog phục vụ nhiều nhu cầu cùng lúc:

| Nhu cầu của nhóm | Backlog giúp gì? | Nếu thiếu hoặc quản lý kém |
| --- | --- | --- |
| **Minh bạch** | Tập hợp và diễn đạt những công việc có thể cần thực hiện, lý do và trạng thái hiểu biết | Yêu cầu nằm rải rác trong tin nhắn, ghi chú và trí nhớ từng người |
| **Tập trung** | Làm rõ việc nào quan trọng nhất trong bối cảnh nguồn lực hữu hạn | Mỗi bên tự xem yêu cầu của mình là cấp bách nhất |
| **Thích ứng** | Thêm, bỏ, chia nhỏ và sắp xếp lại hạng mục theo phản hồi | Nhóm tiếp tục làm điều đã không còn tạo giá trị |
| **Phối hợp** | Tạo ngôn ngữ chung giữa sản phẩm, kỹ thuật, người dùng và bên liên quan | “Đã hiểu yêu cầu” nhưng mỗi người hình dung một kết quả khác |
| **Học hỏi** | Ghi nhận giả định và những việc cần kiểm chứng trước khi cam kết nhiều | Quyết định dựa trên dự đoán chưa được thử |
| **Dự báo** | Cung cấp thông tin về phạm vi, độ rõ, phụ thuộc và năng lực hoàn thành | Lịch giao hàng chỉ là cam kết áp đặt từ một danh sách cố định |
| **Chất lượng** | Không để công việc bảo mật, lỗi, vận hành và nợ kỹ thuật quan trọng biến mất | Sản phẩm tăng tính năng nhưng giảm khả năng phát triển bền vững |

**Backlog không tự tạo ra sự linh hoạt.** Chỉ khi nhóm có quyền và thói quen kiểm tra lại thứ tự dựa trên mục tiêu, dữ liệu và rủi ro, backlog mới trở thành cơ chế học hỏi của Agile.

## 2. Backlog là gì và không phải là gì?

Trong nghĩa rộng, *backlog* là tập các hạng mục có thể cần được thực hiện, chưa hoàn tất, được quản lý để đưa ra lựa chọn công việc. Tên gọi và mức quy định khác nhau giữa các phương pháp.

Trong **Scrum**, **Product Backlog** là một danh sách **có thứ tự, luôn phát triển** về những gì cần để cải thiện sản phẩm; đó là **nguồn duy nhất của công việc Scrum Team thực hiện nhằm cải thiện sản phẩm**. Nó thể hiện các lựa chọn hướng tới **Product Goal**, nhưng không phải mọi hạng mục đều chắc chắn sẽ được triển khai.

Phân biệt những công cụ dễ bị gọi chung là backlog:

| Công cụ | Câu hỏi chính | Đặc điểm |
| --- | --- | --- |
| **Product Backlog** | Sản phẩm nên cải thiện điều gì tiếp theo để tiến gần mục tiêu? | Chứa các hạng mục có thứ tự; được làm rõ và cập nhật liên tục |
| **Sprint Backlog** trong Scrum | Trong Sprint này, Developers sẽ thực hiện kế hoạch nào để đạt Sprint Goal? | Gồm Sprint Goal, các Product Backlog Item được chọn cho Sprint và kế hoạch thực hiện; Developers sở hữu việc điều chỉnh |
| **Danh sách yêu cầu đầu vào** (*intake*) | Những đề xuất, lỗi và phản hồi nào mới được gửi tới? | Có thể chưa xác minh, còn trùng lặp hoặc chưa phù hợp để đưa vào Product Backlog |
| **Roadmap sản phẩm** | Định hướng và những kết quả/mốc lớn dự kiến qua thời gian là gì? | Truyền đạt hướng đi và dự kiến; mức cam kết phụ thuộc bối cảnh |
| **Bảng Kanban** | Công việc hiện đang ở bước nào, bị tắc ở đâu và năng lực còn lại ra sao? | Thể hiện dòng công việc, chính sách kéo việc và WIP; có thể kết hợp hàng đợi chọn việc |
| **Danh sách thao tác cá nhân** | Hôm nay tôi cần xử lý những bước nhỏ nào? | Phục vụ công việc cá nhân, chưa đủ để thay thế ưu tiên sản phẩm chung |

Trong Scrum, Product Backlog và Sprint Backlog là **hai artifact khác nhau**, không nên dùng thuật ngữ thay thế cho nhau. Một nhóm sử dụng Kanban có thể có hàng đợi lựa chọn công việc riêng mà không gọi là Product Backlog theo định nghĩa Scrum.

### 2.1. Backlog không phải hợp đồng cố định về tất cả tính năng

Một bản backlog dài với từng hạng mục được gán ngày hoàn thành chắc chắn có thể tạo cảm giác đã kiểm soát hết tương lai. Nhưng nhu cầu, công nghệ, rủi ro và năng lực nhóm vẫn thay đổi. Trong môi trường bất định, **phạm vi chi tiết ở xa thường là dự đoán, không phải sự thật đã kiểm chứng**.

Điều này không có nghĩa mọi cam kết đều có thể tự ý thay đổi. Nhóm vẫn có thể phải tuân thủ hợp đồng, hạn pháp lý, ngân sách và các nghĩa vụ đã thống nhất. Backlog giúp **nhìn thấy và quản lý những cam kết đó** khi lập kế hoạch, thay vì ngụy trang mọi ý tưởng thành việc bắt buộc.

### 2.2. Backlog không phải kho chứa mọi ý tưởng mãi mãi

Nếu mỗi đề xuất được thêm vào và không bao giờ xóa, backlog sẽ ngày càng nhiễu. Các hạng mục cũ không còn gắn với Product Goal nên được xem xét loại bỏ, hợp nhất, lưu trữ ở nơi thích hợp hoặc đưa về danh sách ý tưởng cần xác minh. Không nên coi số lượng hạng mục tồn đọng là chỉ báo rằng sản phẩm có nhiều giá trị.

## 3. Những thuộc tính làm backlog hữu ích cho ra quyết định

Một Product Backlog tốt không nhất thiết phải có nhiều trường thông tin. Điều quan trọng là những người liên quan **hiểu đủ về từng lựa chọn để xác định giá trị, rủi ro và bước tiếp theo**.

### 3.1. Có thứ tự, không chỉ có nhãn ưu tiên

Một danh sách mà mọi mục đều gắn nhãn “High” không giúp nhóm chọn việc tiếp theo. **Thứ tự** cho biết việc nào nên được xem xét trước, dựa trên hiểu biết và ràng buộc hiện tại. Không nhất thiết tất cả hạng mục xa đều được sắp với độ chính xác giả tạo; phần gần được triển khai nên rõ hơn.

### 3.2. Minh bạch và dễ hiểu

Người xem cần biết mục đích, kết quả mong muốn và trạng thái hiểu biết. Những tên như “Update API v2”, “Fix UI” hoặc “NFR” thiếu ngữ cảnh. Một mô tả như “Học viên không thể hủy đăng ký của người khác, dù thay đổi ID yêu cầu” giúp các bên hiểu rõ hơn giá trị và cách kiểm chứng.

### 3.3. Luôn phát triển theo bằng chứng

Backlog thay đổi khi nhóm hiểu hơn về người dùng, khi có Increment hoạt động được, khi xuất hiện rủi ro hoặc khi mục tiêu sản phẩm đổi. **Thêm, bỏ, gộp, tách, làm rõ và sắp thứ tự lại** đều là hoạt động bình thường.

### 3.4. Phản ánh đủ loại công việc để cải thiện sản phẩm

Backlog không chỉ chứa yêu cầu giao diện. Nó có thể phản ánh lỗi, cải thiện khả năng dùng, công việc chất lượng, bảo mật, vận hành, xử lý nợ kỹ thuật, khám phá nhu cầu và rủi ro tích hợp, miễn mỗi hạng mục có lý do liên quan tới sản phẩm.

### 3.5. Phù hợp năng lực và phạm vi quyết định

Một backlog xếp theo thứ tự nhưng không xét phụ thuộc và năng lực sẽ gây tắc. Ví dụ, tính năng nhắc lịch phụ thuộc vào dữ liệu đăng ký chính xác; xây thông báo trước khi đảm bảo dữ liệu đúng có thể tạo thêm lỗi. Người chịu trách nhiệm cần đưa các phụ thuộc thực sự vào thảo luận, không biến phụ thuộc thành lý do trì hoãn mọi việc.

## 4. Một Product Backlog Item nên chứa những gì?

Trong Scrum, **Product Backlog Item (PBI)** là hạng mục trong Product Backlog. Scrum không yêu cầu PBI phải được viết thành user story hoặc theo một mẫu trường thông tin cố định. PBI có thể mô tả tính năng, lỗi, cải tiến kỹ thuật hay một công việc làm rõ rủi ro.

Ví dụ một PBI:

> **Học viên được xác nhận đăng ký workshop còn chỗ và nhận trạng thái rõ ràng.**

Thông tin có ích để cùng thảo luận:

| Trường thông tin | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Tên và mục đích** | Tại sao công việc này cần thiết? | Giúp học viên đăng ký mà không cần nhân viên hỗ trợ |
| **Người hưởng giá trị** | Ai bị ảnh hưởng? | Học viên đăng ký workshop; bộ phận điều phối |
| **Kết quả mong muốn** | Sau khi hoàn thành, điều gì tốt hơn? | Đăng ký đúng chỗ, trạng thái dễ hiểu và ít xử lý thủ công |
| **Phạm vi ban đầu** | Trong lát cắt đầu tiên, hệ thống hỗ trợ gì? | Học viên đủ điều kiện, một loại workshop, một luồng xác nhận |
| **Tiêu chí chấp nhận** | Hành vi nào phải đúng để công việc đạt yêu cầu? | Không xác nhận vượt số chỗ; lỗi có thông báo; chỉ người đủ quyền đăng ký |
| **Rủi ro/giả định** | Điều gì còn chưa chắc chắn? | Đồng thời nhiều yêu cầu có làm dữ liệu lệch không? |
| **Phụ thuộc** | Cần điều kiện nào hoặc phối hợp với ai? | Dữ liệu lịch trống, chính sách đăng ký, dịch vụ thông báo |
| **Độ lớn/ước lượng khi cần** | Công việc có quá lớn để hoàn thành và kiểm chứng sớm? | Nhóm Developers cùng ước lượng hoặc chia nhỏ |
| **Thứ tự hiện tại** | Vì sao làm trước/sau hạng mục khác? | Đây là luồng giá trị cốt lõi và rủi ro sai dữ liệu cao |
| **Bằng chứng** | Làm sao biết tạo ra giá trị? | Kiểm thử đầu cuối và quan sát đăng ký hợp lệ trong lần sử dụng đầu |

**Không phải mọi trường đều cần điền đầy đủ ngay khi tạo hạng mục.** Với ý tưởng còn xa, tên và lý do tồn tại có thể đủ. Khi hạng mục tiến gần khả năng được chọn triển khai, nhóm làm rõ thêm hành vi, rủi ro và độ lớn. Đó là cách đầu tư công sức làm rõ theo thời điểm cần thiết.

### User story là một cách diễn đạt, không phải toàn bộ backlog

User story thường dùng mẫu:

> **Là** học viên muốn tham gia workshop, **tôi muốn** biết những buổi còn chỗ và đăng ký, **để** tự sắp xếp lịch học.

User story giúp mở cuộc trao đổi về người dùng và giá trị, nhưng không tự chứa đủ mọi quy tắc. Những tiêu chí chấp nhận có thể là:

~~~gherkin
Feature: Dang ky workshop

  Scenario: Dang ky khi con cho
    Given hoc vien A da dang nhap va du dieu kien
    And workshop W con cho trong
    When hoc vien A gui yeu cau dang ky hop le
    Then he thong xac nhan dang ky cho A
    And A nhan duoc trang thai ro rang

  Scenario: Hai hoc vien tranh cho cuoi cung
    Given workshop W chi con mot cho
    When hai hoc vien gui yeu cau gan nhu dong thoi
    Then tong so dang ky duoc xac nhan khong vuot suc chua
    And yeu cau khong thanh cong co thong bao phu hop
~~~

Đây là **ví dụ hành vi** để thảo luận và kiểm thử, không quy định cách khóa dữ liệu hoặc kiến trúc cụ thể. Một hạng mục bảo mật như “ngăn truy cập đăng ký của người khác” cũng có thể được mô tả bằng lỗi, kịch bản tấn công hoặc tiêu chí hệ thống, không nhất thiết ép vào câu “Là một người dùng...”.

## 5. Backlog gắn với Product Goal và kết quả người dùng

Một Product Backlog nên giúp nhóm **đi tới mục tiêu sản phẩm**, không chỉ tạo ra nhiều tính năng. Trong Scrum Guide 2020, **Product Goal** mô tả trạng thái tương lai của sản phẩm và là **commitment của Product Backlog**.

Ví dụ:

> **Product Goal minh họa:** Học viên có thể tự tìm, đăng ký và quản lý workshop phù hợp, với trạng thái đáng tin cậy, để giảm nhu cầu điều phối thủ công.

Product Goal định hướng **vì sao** nhóm làm công việc. Các PBI là những lựa chọn **có thể** giúp tiến tới mục tiêu. Khi phản hồi cho thấy một phương án không còn phù hợp, nhóm có thể bỏ hạng mục đó mà vẫn theo đuổi Product Goal.

### Tách đầu ra và kết quả

| Loại thông tin | Ví dụ | Ý nghĩa |
| --- | --- | --- |
| **Output**: phần được tạo | Hoàn thành trang lịch tháng và API đăng ký | Cho biết phần mềm có thêm khả năng gì |
| **Outcome**: hành vi hoặc vấn đề được cải thiện | Học viên đăng ký thành công mà không cần hỗ trợ; số xác nhận trùng chỗ giảm | Cho biết giá trị người dùng và nghiệp vụ có xuất hiện không |
| **Impact**: ảnh hưởng lâu dài | Khả năng tiếp cận workshop tăng; công việc điều phối giảm theo thời gian | Cho biết sản phẩm có đóng góp vào mục tiêu lớn hơn không |

Nhóm có thể hoàn thành toàn bộ các PBI đã viết mà vẫn chưa đạt kết quả mong muốn. **Backlog phải có khả năng thay đổi để phục vụ mục tiêu**, thay vì biến việc hoàn thành chính backlog thành mục tiêu cuối cùng.

## 6. Các loại công việc nên được nhìn thấy trong backlog

Một backlog chỉ ưu tiên những tính năng “trông thấy được” sẽ khiến nhóm thiếu thời gian để giữ chất lượng và giảm rủi ro. Với sản phẩm đăng ký workshop, có thể phân biệt:

| Loại hạng mục | Ví dụ | Lý do nằm trong backlog |
| --- | --- | --- |
| **Giá trị trực tiếp cho người dùng** | Tìm workshop còn chỗ, đăng ký, tự hủy | Người dùng hoàn thành tác vụ tốt hơn |
| **Cải thiện trải nghiệm** | Hiển thị trạng thái chờ/xác nhận dễ hiểu trên điện thoại | Giảm nhầm lẫn và tăng khả năng sử dụng |
| **Sửa lỗi** | Sửa trường hợp tính sai số chỗ sau khi hủy | Bảo vệ tính đúng đắn và niềm tin |
| **Bảo mật và quyền riêng tư** | Ngăn người học sửa đăng ký của người khác | Giảm rủi ro dữ liệu và đáp ứng ràng buộc |
| **Khả năng vận hành** | Theo dõi lỗi đăng ký và tạo cảnh báo | Phát hiện và xử lý sự cố nhanh hơn |
| **Cải tiến kỹ thuật** | Tách logic kiểm soát chỗ để dễ kiểm thử | Giảm chi phí thay đổi và rủi ro hồi quy |
| **Khám phá và kiểm chứng giả định** | Thử bản mẫu lịch tháng so với danh sách giờ trống | Tránh đầu tư lớn vào cách dùng chưa chắc phù hợp |
| **Khả thi kỹ thuật (*spike*)** | Thử phương án xử lý hai yêu cầu đồng thời | Giảm bất định trước khi quyết định kiến trúc |

Không nhất thiết biến **mọi thao tác kiểm thử, code review hay kiểm tra bảo mật nhỏ** thành PBI riêng. Những điều cần thiết để một lát cắt chức năng trở thành Increment hoàn chỉnh nên nằm trong **tiêu chí chấp nhận và Definition of Done**. Hạng mục độc lập phù hợp khi có công việc hoặc năng lực cần lập kế hoạch riêng, ví dụ triển khai hệ thống giám sát dùng chung.

## 7. Sắp thứ tự backlog để chọn việc đáng làm tiếp

**Có thứ tự** khác với việc công việc nào “nghe hấp dẫn” được kéo lên đầu. Nhóm cần cân nhắc đồng thời giá trị, rủi ro, thời điểm, độ lớn và phụ thuộc.

### 7.1. Các yếu tố thường được dùng

| Yếu tố | Câu hỏi hữu ích | Ví dụ |
| --- | --- | --- |
| **Giá trị người dùng/nghiệp vụ** | Việc này giúp ai làm điều gì tốt hơn? | Đăng ký đáng tin cậy là luồng cốt lõi |
| **Rủi ro nếu không làm** | Thiệt hại hoặc bất định lớn tới đâu nếu trì hoãn? | Xác nhận vượt số chỗ gây sai dữ liệu và khiếu nại |
| **Tính cấp thời** | Có hạn cam kết, sự kiện thị trường hay phụ thuộc thời gian? | Workshop sắp mở đăng ký cho học kỳ mới |
| **Công sức và độ lớn** | Có thể chia để giao phần giá trị nhỏ hơn không? | Xây cả dashboard có thể lớn hơn việc hiển thị trạng thái |
| **Phụ thuộc** | Điều gì phải có trước để làm hoặc kiểm chứng an toàn? | Cần xác định trạng thái đăng ký trước khi gửi email theo trạng thái |
| **Giá trị học hỏi** | Phép thử nào giúp quyết định tốt hơn và tránh làm lại? | Thử danh sách khung giờ với người dùng trước khi xây lịch tháng |
| **Năng lực nhóm** | Có chuyên môn và môi trường để hoàn tất không? | Cần chuyên gia tích hợp khi thay đổi hợp đồng API |

Không phải mọi yếu tố có thể quy về một phép tính chính xác. Điểm số đôi khi có ích để thảo luận, nhưng **không thay thế phán đoán và trách nhiệm ra quyết định**.

### 7.2. Ví dụ thứ tự trước và sau phản hồi

**Thứ tự ban đầu (minh họa):**

| Thứ tự | Hạng mục | Giả định chính |
| ---: | --- | --- |
| 1 | Giao diện lịch tháng kéo thả | Người học cần nhìn tháng và thao tác trên lịch |
| 2 | Bộ lọc theo mentor và chủ đề | Nhiều lựa chọn nên cần bộ lọc phức tạp |
| 3 | Đăng ký một chỗ còn trống | Người học cần tự xác nhận |
| 4 | Email xác nhận | Email là cách người học biết đã đăng ký |
| 5 | Chức năng tự hủy | Bộ phận hỗ trợ xử lý thủ công vẫn chấp nhận được trong giai đoạn đầu |

Sau thử bản mẫu và xem dữ liệu hỗ trợ, nhóm phát hiện người học dùng điện thoại, ưu tiên trạng thái đặt chỗ rõ ràng, còn nhân viên thường giải quyết hủy thủ công.

**Thứ tự mới đề xuất (minh họa):**

| Thứ tự | Hạng mục | Lý do sắp xếp |
| ---: | --- | --- |
| 1 | Đăng ký chỗ hợp lệ, chống vượt sức chứa, hiển thị kết quả rõ | Giá trị cốt lõi và rủi ro dữ liệu cao |
| 2 | Xem đăng ký của mình và tự hủy đúng chính sách | Giảm thao tác hỗ trợ, giải quyết vấn đề đã quan sát |
| 3 | Kiểm tra và cải thiện luồng chọn giờ trên điện thoại | Phản hồi cho thấy trải nghiệm ban đầu chưa phù hợp |
| 4 | Thông báo xác nhận theo trạng thái thật | Giá trị bổ sung sau khi trạng thái dữ liệu đáng tin |
| 5 | Bộ lọc nâng cao hoặc lịch tháng | Chờ thêm bằng chứng về nhu cầu và mức giá trị |

Nhóm **không từ bỏ mục tiêu sản phẩm**; họ điều chỉnh con đường tới mục tiêu. Đây là vai trò trung tâm của backlog trong phát triển thích ứng.

### 7.3. Khi các bên đều nói “việc của tôi là ưu tiên một”

Cuộc trao đổi có thể theo các bước:

1. Nhắc lại Product Goal hoặc kết quả cần đạt.
2. Hỏi mỗi yêu cầu tạo giá trị gì, cho ai, vào thời điểm nào.
3. Nêu rủi ro và chi phí nếu trì hoãn hoặc làm sai.
4. Đánh giá có thể tách một lát cắt nhỏ để giao hoặc thử trước không.
5. Công khai thứ tự hiện tại và lý do, ghi những điều cần kiểm chứng.
6. Xác định ai chịu trách nhiệm chốt khi không thể đồng thuận.

Trong Scrum, **Product Owner chịu trách nhiệm quản lý Product Backlog hiệu quả**, bao gồm sắp xếp Product Backlog Item; họ có thể ủy quyền thực hiện một số công việc quản lý nhưng vẫn chịu trách nhiệm kết quả. Điều đó **không yêu cầu Product Owner tự mình nghĩ ra mọi PBI**: Developers, người dùng và bên liên quan cung cấp thông tin quan trọng.

## 8. Refinement: làm rõ vừa đủ trước khi thực hiện

**Product Backlog Refinement** là hoạt động liên tục chia nhỏ và làm rõ các PBI, thường bổ sung chi tiết, thứ tự và độ lớn khi cần. Trong Scrum, refinement **không phải một sự kiện chính thức có timebox cố định** như Sprint Planning hay Sprint Review.

Mục tiêu refinement là tạo **sự hiểu biết chung đủ để lựa chọn và thực hiện công việc**, không phải viết đặc tả chi tiết cho toàn bộ tương lai.

### 8.1. Nguyên tắc “gần rõ hơn, xa có thể mờ hơn”

| Khoảng cách tới khả năng triển khai | Mức thông tin hợp lý |
| --- | --- |
| **Đang khám phá/ở xa** | Tên, lý do, người dùng hoặc rủi ro chính, giả định chưa biết; có thể chưa ước lượng |
| **Có thể được chọn sớm** | Hành vi cần có, những ví dụ quan trọng, tiêu chí chấp nhận, phụ thuộc, rủi ro và độ lớn tương đối |
| **Được chọn vào Sprint hoặc bắt đầu làm** | Mục đích rõ, kế hoạch thực hiện khả thi, chất lượng và ranh giới đã thống nhất; vẫn có thể điều chỉnh khi học thêm |

Nếu làm rõ mọi hạng mục 12 tháng tới tới mức mô tả từng màn hình và từng API, nhóm có thể mất nhiều thời gian cho những ý tưởng sẽ thay đổi hoặc không bao giờ được thực hiện.

### 8.2. Kỹ thuật chia nhỏ công việc

Một PBI “Quản lý toàn bộ workshop” thường quá rộng để hoàn thành và nhận phản hồi sớm. Có thể chia theo:

- **Luồng người dùng:** Xem workshop; đăng ký; xem đăng ký; hủy theo điều kiện.
- **Kịch bản:** Đăng ký hợp lệ trước, rồi mở rộng chính sách ngoại lệ; không trì hoãn những kiểm soát an toàn bắt buộc.
- **Nhóm người dùng:** Thử với học viên của một khóa hoặc một loại workshop trước khi mở rộng.
- **Biến thể nghiệp vụ:** Workshop miễn phí trước; thanh toán và hoàn tiền thành lát cắt hoàn chỉnh sau nếu chưa thuộc phạm vi đầu.
- **Giả định cần học:** Thử bản mẫu lịch tháng hay danh sách giờ để quyết định giao diện.
- **Phạm vi tích hợp:** Một luồng thông báo được kiểm chứng trước khi thêm nhiều kênh và chính sách.

**Chia theo lát cắt dọc** (*vertical slice*) thường có ích hơn việc chia thành “xong hết giao diện”, “xong hết API”, “xong hết cơ sở dữ liệu” nếu mục tiêu là sớm có phần mềm mà người dùng đánh giá được.

### 8.3. Definition of Ready có bắt buộc không?

Một số nhóm dùng tiêu chí **Definition of Ready (DoR)** như thỏa thuận nội bộ để xác định PBI đủ rõ trước khi bắt đầu. DoR **không phải artifact hoặc cam kết bắt buộc trong Scrum Guide 2020**. Nếu dùng, nó cần hỗ trợ trao đổi và phát hiện rủi ro; tránh biến thành cổng phê duyệt cứng khiến mọi PBI phải có tài liệu dày, làm chậm khả năng học hỏi.

**Definition of Done (DoD)** lại là cam kết của **Increment** trong Scrum, mô tả trạng thái đáp ứng các tiêu chuẩn chất lượng. Không nên nhầm một PBI “đủ rõ để bắt đầu” với Increment “đã hoàn thành đúng chất lượng”.

## 9. Backlog và vòng lặp phản hồi trong phát triển tăng dần

Backlog là điểm nối giữa **điều nhóm tin sẽ tạo giá trị** và **điều thực tế cho thấy có giá trị**. Một vòng thích ứng có thể mô tả như sau:

~~~mermaid
flowchart LR
    A["Product Goal và nhu cầu người dùng"] --> B["Product Backlog có thứ tự"]
    B --> C["Chọn lát cắt / giả thuyết cần kiểm chứng"]
    C --> D["Xây, tích hợp và kiểm thử"]
    D --> E["Increment hoạt động được / bản thử phù hợp"]
    E --> F["Quan sát, đo lường và phản hồi"]
    F --> G["Quyết định giữ, sửa, bỏ, thêm, đổi thứ tự"]
    G --> B
~~~

Vòng lặp quan trọng là **từ bằng chứng quay lại quyết định backlog**. Nếu nhóm demo sản phẩm hằng tuần nhưng không thay đổi ưu tiên khi phản hồi cho thấy nhu cầu khác, hoạt động phản hồi chưa thực sự giúp nhóm thích ứng.

### 9.1. Mỗi lần xem xét nên phân biệt bốn loại thông tin

| Loại | Câu hỏi |
| --- | --- |
| **Điều biết chắc từ quan sát** | Người dùng đã thao tác thế nào? Hệ thống có lỗi gì? |
| **Diễn giải và giả định** | Vì sao họ dừng ở bước chọn giờ? Có phải do giao diện hay do hết chỗ? |
| **Quyết định hiện tại** | Sửa trạng thái, tăng thử nghiệm, ưu tiên hủy hay mở rộng bộ lọc? |
| **Điều cần học tiếp** | Cần đo hành vi nào hoặc thử phương án gì để giảm bất định? |

Một buổi phản hồi tốt có thể dẫn tới quyết định **không làm một PBI** nữa. Đây vẫn là kết quả hữu ích: nhóm tiết kiệm công sức trước khi xây thứ không tạo giá trị.

### 9.2. Khác biệt giữa “hoàn thành công việc” và “xác nhận kết quả”

Hãy tưởng tượng PBI “thêm email nhắc workshop” đã được giao và kiểm thử. Nhóm đánh dấu hoàn thành công việc kỹ thuật đúng tiêu chí. Nhưng nếu sau vài tuần không có khác biệt rõ ràng về tỷ lệ tham dự, giả thuyết “email sẽ giúp giảm bỏ lỡ” **chưa được xác nhận**.

Do đó:

- **Kiểm chứng hạng mục:** Phần mềm làm đúng những hành vi đã thống nhất và đạt tiêu chuẩn hoàn thành chưa?
- **Kiểm chứng giả thuyết:** Hành vi người dùng và kết quả có thay đổi như kỳ vọng không?

Hai việc bổ trợ nhau và có thể kết thúc ở những thời điểm khác nhau. Không nên giữ một Increment đã đạt DoD trong trạng thái “chưa hoàn thành” chỉ vì phép đo tác động dài hạn chưa đủ thời gian; thay vào đó tạo kế hoạch đo lường và quyết định tiếp theo minh bạch.

## 10. Trách nhiệm với Product Backlog trong Scrum

Scrum giúp minh họa rõ trách nhiệm mà không cần biến backlog thành công cụ quản lý vi mô.

| Chủ thể | Trách nhiệm liên quan tới backlog | Điều cần tránh |
| --- | --- | --- |
| **Product Owner** | Chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả: phát triển/truyền đạt Product Goal, tạo và truyền đạt PBI rõ ràng, sắp thứ tự, đảm bảo minh bạch, hiển thị và được hiểu | Chỉ ghi nhận mọi yêu cầu mà không đưa ra lựa chọn ưu tiên |
| **Developers** | Tham gia làm rõ, đánh giá độ lớn và tính khả thi; chọn PBI trong Sprint Planning; tạo và điều chỉnh Sprint Backlog để đạt Sprint Goal; bảo đảm chất lượng Increment | Nhận danh sách công việc như mệnh lệnh bất biến hoặc tự đổi ưu tiên sản phẩm mà không phối hợp |
| **Scrum Master** | Hỗ trợ Scrum Team áp dụng Scrum, giúp Product Owner và tổ chức nâng cao thực hành quản lý Product Backlog, tháo gỡ trở ngại | Trở thành người duyệt mọi PBI hoặc áp thứ tự thay Product Owner |
| **Người dùng và bên liên quan** | Cung cấp bối cảnh, phản hồi, dữ liệu, ràng buộc và kiến thức nghiệp vụ | Mặc định mọi đề xuất đều lập tức trở thành yêu cầu cam kết |

Scrum Team tự quản cách thực hiện công việc bên trong phạm vi trách nhiệm. Product Owner vẫn chịu trách nhiệm về Product Backlog; Developers chịu trách nhiệm tổ chức công việc Sprint và tạo Increment đạt DoD. Sự phân vai này tạo **cơ chế phối hợp**, không phải rào chắn giữa “người viết yêu cầu” và “người code”.

### 10.1. Product Backlog và Sprint Backlog liên hệ ra sao?

Trong Sprint Planning, Scrum Team cùng làm rõ **vì sao Sprint có giá trị**, Developers cùng Product Owner trao đổi để chọn **những PBI có thể thực hiện**, rồi Developers lập kế hoạch **làm thế nào** để tạo Increment. Kết quả hình thành Sprint Backlog với **Sprint Goal, các PBI được chọn và kế hoạch triển khai**.

~~~mermaid
flowchart TD
    A["Product Goal"] --> B["Product Backlog có thứ tự"]
    B --> C["Sprint Planning: vì sao, làm gì, làm thế nào"]
    C --> D["Sprint Goal"]
    C --> E["PBI được chọn cho Sprint"]
    C --> F["Kế hoạch thực hiện"]
    D --> G["Sprint Backlog của Developers"]
    E --> G
    F --> G
    G --> H["Increment đạt Definition of Done"]
    H --> I["Sprint Review và các phản hồi khác"]
    I --> B
~~~

**Sprint Goal** là *commitment* của Sprint Backlog. Khi nhóm học thêm, Sprint Backlog có thể được điều chỉnh; phạm vi có thể được làm rõ và thương lượng với Product Owner trong Sprint. Tuy nhiên, không nên đưa thêm việc thiếu kiểm soát làm nguy hại Sprint Goal hoặc giảm chất lượng để giữ một kế hoạch đã lỗi thời.

### 10.2. Backlog không phải thước đo năng suất cá nhân

Đếm số PBI hoàn thành không đo trực tiếp giá trị: một PBI lớn có thể có nhiều rủi ro, nhiều tác động hơn nhiều PBI nhỏ. Dùng story point để xếp hạng cá nhân dễ khiến nhóm chia nhỏ giả tạo, né lỗi khó và bỏ chất lượng. Backlog nên giúp **toàn nhóm chọn và hoàn thành giá trị**, không trở thành bảng thành tích từng người.

## 11. Backlog trong Kanban và nhóm không dùng Sprint

Kanban tập trung vào **trực quan hóa công việc, quản lý dòng chảy, giới hạn WIP, chính sách rõ ràng và cải tiến theo dữ liệu**. Một nhóm có thể kéo công việc từ hàng đợi khi đủ năng lực, thay vì chờ một Sprint mới.

Ví dụ bảng công việc:

| Sẵn sàng lựa chọn | Đang phát triển | Đang kiểm chứng | Sẵn sàng bàn giao |
| --- | --- | --- | --- |
| Sửa thông báo lỗi đăng ký | Lát cắt tự hủy workshop | Kiểm tra chống xác nhận trùng | Xem đăng ký của mình |

Mỗi cột cần có **chính sách vào/ra rõ**, và nhóm có thể giới hạn WIP để tránh mở nhiều việc cùng lúc. Hàng đợi đầu vào của hệ thống Kanban có thể được quản lý theo ưu tiên sản phẩm; Kanban không buộc phải dùng tên gọi, vai trò hay artifact giống Scrum.

### Hai câu hỏi bổ trợ khi quản lý backlog theo dòng công việc

1. **Hàng đợi được bổ sung khi nào và theo chính sách nào?** Nếu nhóm luôn kéo việc mới vào trong khi công việc kiểm chứng đang tắc, dòng chảy sẽ chậm.
2. **Khi nào phải xem lại thứ tự?** Ví dụ khi xuất hiện lỗi nghiêm trọng, yêu cầu khẩn cấp, thay đổi chiến lược hoặc bằng chứng mới từ người dùng.

Các chỉ số như WIP, throughput, work item age và cycle time giúp thấy năng lực hoàn tất và điểm nghẽn. Chúng hỗ trợ dự báo **dòng công việc**, nhưng không tự chứng minh backlog đang chứa đúng những việc tạo giá trị.

## 12. Backlog, roadmap và lập kế hoạch thích ứng

Roadmap và backlog nên hỗ trợ lẫn nhau:

- **Roadmap:** Nêu hướng đi, vấn đề ưu tiên, mục tiêu và những mốc dự kiến để các bên phối hợp.
- **Product Backlog:** Diễn đạt và sắp xếp những lựa chọn cụ thể hơn để tiến tới mục tiêu.
- **Kế hoạch Sprint hoặc chính sách kéo việc:** Biến các lựa chọn gần thành công việc thực hiện có thể kiểm chứng.

Ví dụ roadmap có mục tiêu “Giảm thời gian điều phối workshop trong quý tới”. Backlog có thể chứa “cho phép học viên tự hủy”, “hiển thị chỗ còn trống chính xác”, “gửi trạng thái rõ ràng”. Sau phản hồi, nhóm có thể đổi thứ tự và lựa chọn tính năng nhưng vẫn hướng tới kết quả đã cam kết.

### Lập kế hoạch với mức chắc chắn phù hợp

Một dự báo có ích cần làm rõ:

| Thành phần | Cần công khai |
| --- | --- |
| **Phạm vi đang dự báo** | Hạng mục nào thực sự cần để đạt một mốc giá trị? Hạng mục nào là tùy chọn? |
| **Dữ liệu năng lực** | Lịch sử hoàn thành công việc, biến động loại việc, phụ thuộc và công việc chưa biết |
| **Điều kiện giả định** | Quy mô đội, sự tham gia của bên nghiệp vụ, khả năng tích hợp, giới hạn chất lượng |
| **Độ bất định** | Những yêu cầu hoặc rủi ro nào còn phải kiểm chứng? |
| **Cơ chế cập nhật** | Khi nào dự báo được xem lại và ai chịu trách nhiệm truyền đạt thay đổi? |

Nếu chưa có dữ liệu tin cậy hoặc nhiều PBI còn quá lớn, **không nên hứa một ngày chính xác từ phép cộng ước lượng sơ bộ**. Có thể dùng mốc có khoảng, kịch bản, lịch sử thông lượng hoặc dự báo xác suất khi đủ dữ liệu và phương pháp phù hợp. Điều quan trọng là phân biệt **cam kết bắt buộc** với **dự báo có điều kiện**.

## 13. Đo lường để đánh giá backlog có đang hỗ trợ thích ứng không

Một backlog “gọn” trên công cụ quản lý chưa chắc tạo giá trị. Các chỉ báo nên kết hợp **khả năng hoàn tất công việc, chất lượng và kết quả người dùng**.

| Góc nhìn | Tín hiệu gợi ý | Cách đọc có trách nhiệm |
| --- | --- | --- |
| **Dòng công việc** | Cycle time, lead time, throughput, WIP và work item age | Xem việc có bị chờ lâu và có hoàn tất ổn định; phải thống nhất mốc đo |
| **Mức tập trung** | Số việc đang làm so với năng lực, mức độ bị ngắt bởi việc khẩn | WIP cao hoặc đổi việc liên tục có thể làm chậm hoàn tất |
| **Chất lượng** | Lỗi sau phát hành, làm lại, rủi ro bảo mật tồn đọng | Nhiều tính năng “Done” không có nghĩa Increment đủ chất lượng |
| **Giá trị cho người dùng** | Tỷ lệ đăng ký thành công, thời gian hoàn thành tác vụ, yêu cầu hỗ trợ | Cho biết công việc đã tác động tới vấn đề thật hay chưa |
| **Học hỏi** | Giả định được kiểm chứng, thay đổi quyết định dựa trên phản hồi | Không chạy theo số lượng thử nghiệm; xem điều gì đã được học và làm khác đi |
| **Khả năng dự báo** | Chênh lệch giữa dự kiến và thực tế, lý do thay đổi, phụ thuộc chưa thấy | Điều chỉnh phương pháp và công bố mức bất định, không tìm người để đổ lỗi |
| **Sức khỏe backlog** | Hạng mục trùng, không còn lý do, tồn quá lâu, không gắn mục tiêu | Dọn thông tin không còn hữu ích; không biến tuổi hạng mục thành lý do tự động loại bỏ |

### Thận trọng với việc “đo số item”

Nếu nhóm chia một user story thành mười hạng mục nhỏ, **số item hoàn tất tăng** dù giá trị không tăng tương ứng. Tương tự, “đã refinement 100 item” chỉ nói nhóm đã tổ chức nhiều cuộc thảo luận, không nói những quyết định đã chính xác hơn.

Để đo dòng chảy theo thời gian, cần thống nhất điểm bắt đầu/kết thúc và cách phân loại công việc. **Lead time** có thể được định nghĩa từ lúc một nhu cầu được nhận tới khi giao giá trị; **cycle time** thường tính từ lúc thực sự bắt đầu xử lý tới khi hoàn tất theo chính sách nhóm. Các hệ thống đo có quy ước khác nhau; không so sánh những con số không cùng định nghĩa.

### Một tín hiệu đáng quan sát

Giả sử throughput tăng nhưng tỷ lệ xác nhận trùng chỗ và số yêu cầu hỗ trợ cũng tăng. Kết luận hợp lý không phải “backlog đang tốt vì làm xong nhiều việc”, mà là cần xem lại **tiêu chí chấp nhận, DoD, thứ tự rủi ro và việc nhóm đã đầu tư đủ vào chất lượng chưa**.

Ngược lại, giảm số PBI hoàn tất trong một giai đoạn nhưng xử lý được lỗi dữ liệu nghiêm trọng và giảm làm lại có thể là lựa chọn tốt. Giá trị không có quan hệ tuyến tính với số hàng trong backlog.

## 14. Những sai lầm thường gặp khi quản lý backlog

| Sai lầm | Hệ quả | Hướng điều chỉnh |
| --- | --- | --- |
| Backlog là bản kế hoạch không được thay đổi | Cơ hội và rủi ro mới không ảnh hưởng tới hành động | Định kỳ xem lại thứ tự theo Product Goal và bằng chứng |
| Mọi yêu cầu đều được đánh dấu “P0” hoặc “High” | Nhóm không có lựa chọn rõ khi năng lực có hạn | Công khai thứ tự, lý do, quyền chốt và cách xử lý yêu cầu khẩn |
| Mọi ý tưởng đều đưa vào backlog rồi giữ mãi | Danh sách nhiễu, refinement tốn thời gian | Lọc đầu vào, gộp/xóa/lưu trữ đề xuất không còn phù hợp |
| Chỉ đưa tính năng vào backlog; lỗi và bảo mật để “làm sau” | Tích tụ rủi ro, mất khả năng giao sản phẩm bền vững | Thể hiện công việc chất lượng, vận hành, nợ kỹ thuật có ý nghĩa |
| Viết chi tiết mọi hạng mục xa trong tương lai | Lãng phí công sức khi nhu cầu đổi | Làm rõ vừa đủ, tăng chi tiết gần thời điểm thực hiện |
| Chia công việc theo tầng kỹ thuật và xem mỗi tầng là giá trị đã giao | Người dùng không có luồng sử dụng hoạt động được | Ưu tiên lát cắt dọc có thể kiểm chứng |
| Product Owner viết hết, Developers chỉ nhận lệnh | Thiếu thông tin kỹ thuật, ước lượng và khả năng triển khai | Refinement và planning có đủ chuyên môn cùng tham gia |
| Developers tự thay ưu tiên sản phẩm không trao đổi | Mục tiêu và kỳ vọng bên liên quan bị lệch | Minh bạch rủi ro và phối hợp đúng vai trò quyết định |
| PBI đã chọn vào Sprint thì không thể thay cách làm | Khó phản ứng với hiểu biết mới | Thích ứng Sprint Backlog để đạt Sprint Goal, phối hợp Product Owner |
| Đổi ưu tiên liên tục mà không có tiêu chí | Người làm việc bị ngắt, nhiều việc dang dở | Nêu lý do, ngưỡng khẩn, chính sách WIP và thời điểm xem xét |
| Dùng story point hoặc số item để xếp hạng người | Tạo động cơ đo sai, chất lượng giảm | Đo dòng giá trị và chất lượng ở cấp nhóm/sản phẩm |
| Sprint Review chỉ xác nhận mọi thứ đã “xong” | Không đưa phản hồi trở lại backlog | Quan sát Increment, đánh giá mục tiêu và cập nhật quyết định |

**Một backlog thay đổi liên tục không tự động thể hiện Agile.** Nếu thay đổi không có mục tiêu, không dựa trên thông tin mới và liên tục phá vỡ tập trung, đó có thể là biểu hiện của quản lý ưu tiên yếu. Thích ứng tốt cần **định hướng ổn định và cơ chế điều chỉnh minh bạch**.

## 15. Quy trình thực hành xây dựng và duy trì backlog

### Bước 1. Thống nhất mục tiêu sản phẩm và vấn đề cần giải quyết

Viết mục tiêu rõ cho nhóm người dùng hoặc nghiệp vụ. Ví dụ: “Học viên tự đăng ký và tự quản lý workshop đáng tin cậy, giảm việc điều phối thủ công”. Xác định giới hạn hiện có: chính sách đăng ký, bảo mật, ngân sách và mốc thời gian bắt buộc.

### Bước 2. Thu thập đề xuất, vấn đề và bằng chứng

Lắng nghe người dùng, Product Owner, Developers, vận hành, hỗ trợ và các nhóm phụ thuộc. Phân biệt **yêu cầu đã biết**, **ý tưởng giải pháp** và **giả định chưa kiểm chứng**. Không để danh sách đầu vào thô trở thành thứ tự công việc đã cam kết.

### Bước 3. Diễn đạt PBI bằng kết quả mong muốn

Tên hạng mục nên nói rõ ai được lợi và điều gì thay đổi. Thay “Làm API registration” bằng “Học viên đủ điều kiện đăng ký được một chỗ còn trống, trạng thái chính xác”, rồi mô tả công việc kỹ thuật cần thiết khi refinement.

### Bước 4. Xác định rủi ro, ràng buộc và phụ thuộc

Mỗi hạng mục gần cần triển khai nên có các ví dụ quan trọng về dữ liệu, quyền và tình huống lỗi; đồng thời làm rõ phụ thuộc giữa các nhóm. Hạng mục chưa chắc khả thi có thể cần spike nhỏ, bản mẫu hoặc phép thử trước.

### Bước 5. Sắp thứ tự trên cơ sở giá trị và chi phí trì hoãn

So sánh những lựa chọn hiện tại: giá trị với người dùng, mức rủi ro, hạn, phụ thuộc và độ lớn. Ghi rõ lý do đưa một việc lên hoặc xuống. Nếu dùng phương pháp chấm điểm, coi điểm số là **công cụ hỗ trợ hội thoại**, không phải máy quyết định.

### Bước 6. Refinement các hạng mục gần và chia lát cắt

Làm rõ tiêu chí chấp nhận, kích thước và giới hạn, chia hạng mục lớn thành phần có thể hoàn thành và đánh giá sớm. Không đặt mục tiêu refinement toàn bộ backlog đến mức chi tiết như nhau.

### Bước 7. Chọn việc theo năng lực và duy trì chất lượng

Trong Scrum, nhóm lập Sprint Goal và Sprint Backlog; trong hệ thống Kanban, kéo việc theo chính sách và WIP. Dù dùng cách nào, công việc chỉ thực sự hoàn thành khi đạt yêu cầu cần thiết, đặc biệt về dữ liệu, bảo mật và chất lượng.

### Bước 8. Giao Increment hoặc kết quả thử nghiệm và thu phản hồi

Quan sát hành vi thực, lỗi, khó khăn người dùng và kết quả đạt được. Bản mẫu có thể giúp khám phá, nhưng không thay thế việc đánh giá Increment hoạt động được khi cần kiểm chứng hành vi trong hệ thống thật.

### Bước 9. Cập nhật backlog và truyền đạt quyết định

Thay thứ tự, thêm/bỏ/gộp/tách hạng mục dựa trên điều đã học. Nếu có cam kết với bên ngoài, trao đổi tác động và kế hoạch điều chỉnh. Ghi lại lý do cho các quyết định quan trọng để mọi người hiểu vì sao danh sách khác trước.

## 16. Mẫu ghi một hạng mục và lý do ưu tiên

Mẫu sau có thể dùng trong công cụ quản lý công việc. Tùy mức rủi ro, không phải trường nào cũng bắt buộc điền ngay.

~~~text
TÊN PBI:
PRODUCT GOAL / MỤC TIÊU LIÊN QUAN:
NGƯỜI DÙNG / BÊN HƯỞNG GIÁ TRỊ:
VẤN ĐỀ CẦN GIẢI QUYẾT:
KẾT QUẢ MONG MUỐN:

PHẠM VI LÁT CẮT:
TIÊU CHÍ CHẤP NHẬN:
RÀNG BUỘC CHẤT LƯỢNG / BẢO MẬT:
GIẢ ĐỊNH VÀ RỦI RO CHÍNH:
PHỤ THUỘC / NGƯỜI CẦN THAM VẤN:

THỨ TỰ HIỆN TẠI:
LÝ DO ĐẶT THỨ TỰ:
ĐỘ LỚN / BẰNG CHỨNG NĂNG LỰC (NẾU CẦN):
MỨC ĐỘ HIỂU BIẾT / ĐIỀU CẦN LÀM RÕ:

BẰNG CHỨNG SAU KHI GIAO HOẶC THỬ:
QUYẾT ĐỊNH: GIỮ / SỬA / CHIA / BỎ / ĐỔI THỨ TỰ
NGƯỜI CHỊU TRÁCH NHIỆM / THỜI ĐIỂM XEM XÉT LẠI:
~~~

Điều quan trọng là **mỗi trường phải hỗ trợ một cuộc trao đổi hoặc quyết định thực tế**. Nếu một trường chỉ được điền vì công cụ yêu cầu mà không ai dùng, nhóm nên cân nhắc đơn giản hóa theo quy định của tổ chức.

## 17. Bài tập tình huống: sắp lại backlog sau phản hồi

**Bối cảnh:** Nhóm phát triển nền tảng học tập có mục tiêu giúp học viên **tiếp tục học đều đặn sau tuần đầu**. Product Backlog ban đầu gồm:

| Mã | Hạng mục | Ghi chú ban đầu |
| --- | --- | --- |
| A | Dashboard tiến độ với nhiều biểu đồ | Bên liên quan tin rằng biểu đồ sẽ tạo động lực |
| B | Nút “Học bài tiếp theo” trên trang hoàn tất bài | Có thể giảm thời gian tìm bài |
| C | Thông báo nhắc học hằng ngày | Chưa biết học viên có muốn bị nhắc thường xuyên không |
| D | Sửa lỗi mất tiến độ khi kết nối không ổn định | Một số học viên phải học lại bài đã hoàn thành |
| E | Bổ sung sự kiện đo việc bắt đầu và hoàn thành bài tiếp theo | Hiện nhóm chỉ có số lần truy cập trang |
| F | Bảng xếp hạng theo điểm | Có ý kiến cho rằng cạnh tranh giúp học nhiều hơn |

Nhóm có ít năng lực, muốn chọn **hai công việc hoặc phép thử tiếp theo**. Phỏng vấn ban đầu cho thấy một số học viên không biết bài nên học tiếp; một nhóm khác bỏ cuộc vì tiến độ bị mất khi đổi thiết bị.

Hãy trả lời:

1. **Product Goal** nên được diễn đạt theo kết quả nào? Trong danh sách, đâu là mục tiêu và đâu chỉ là phương án?
2. Bạn sẽ ưu tiên xử lý **D** như thế nào nếu lỗi mất tiến độ khiến người dùng mất niềm tin? Lỗi này có thể được xem là “phần kỹ thuật không tạo giá trị” không?
3. Hạng mục **E** giúp nhóm học điều gì trước khi mở rộng B hoặc C?
4. Với **A, C và F**, có thể dùng thử nghiệm nhỏ nào để giảm rủi ro xây nhầm?
5. Nếu PBI **B** được chọn, bạn sẽ chia lát cắt đầu tiên ra sao và cần tiêu chí chấp nhận gì để không đưa người học tới bài không hợp lệ?
6. Sau một bản thử, nút “Học tiếp” tăng lượt nhấp nhưng tỷ lệ hoàn thành bài tiếp theo không tăng. Bạn sẽ cập nhật backlog và giả thuyết thế nào?
7. Nếu có bên liên quan yêu cầu làm F ngay vì “đã hứa từ đầu năm”, bạn cần làm rõ điều gì về cam kết, giá trị và thẩm quyền?

### Gợi ý hướng giải

Mục tiêu có thể là “Người học tìm được lộ trình tiếp theo phù hợp và duy trì tiến trình học mà không mất dữ liệu”. Với thông tin đã có, **D** là rủi ro chất lượng trực tiếp cần được xem xét rất sớm; **E** tạo khả năng đo hành vi thật. Nhóm có thể phát triển một lát cắt nhỏ của **B** với lựa chọn bài kế tiếp đúng điều kiện và theo dõi hành vi. **A, C, F** là các phương án còn cần kiểm chứng; không mặc nhiên phải xây đầy đủ. Nếu lượt nhấp tăng mà học tiếp không cải thiện, cần phân tích cơ chế tác động, độ khó bài, chất lượng dữ liệu và ngữ cảnh. Thứ tự chính xác phụ thuộc hậu quả lỗi, cam kết bắt buộc, năng lực và kết quả thử; một câu trả lời tốt phải **giải thích được lý do và điều kiện xem xét lại**, thay vì chỉ gán nhãn P0/P1.

## 18. Ghi nhớ và tự kiểm tra

**Backlog là công cụ quản lý các lựa chọn để cải thiện sản phẩm trong điều kiện hiểu biết thay đổi.** Vai trò quan trọng nhất của nó là nối mục tiêu, ưu tiên, năng lực thực hiện và bằng chứng từ người dùng thành một vòng ra quyết định liên tục. Product Backlog cần minh bạch, có thứ tự và luôn phát triển; các hạng mục gần được làm rõ vừa đủ, còn những lựa chọn xa có thể chờ bằng chứng trước khi cam kết sâu.

Tự kiểm tra:

1. Vì sao backlog không nên được hiểu là hợp đồng cố định phải hoàn thành mọi hạng mục?
2. Product Backlog khác Sprint Backlog và roadmap ở mục đích, quyền quyết định và mức chi tiết như thế nào?
3. Khi nào nên tạo một PBI khám phá hoặc spike thay vì bắt đầu xây cả giải pháp?
4. Vì sao lỗi dữ liệu, bảo mật và khả năng vận hành cũng có thể cần được ưu tiên trong backlog?
5. Một user story đã viết đúng mẫu “Là..., tôi muốn..., để...” có đủ để bắt đầu triển khai chưa? Cần trao đổi thêm gì?
6. Tại sao Product Owner chịu trách nhiệm thứ tự Product Backlog nhưng vẫn cần Developers và bên liên quan tham gia refinement?
7. Refinement khác với yêu cầu viết đặc tả tất cả tính năng ngay từ đầu ở điểm nào?
8. Trong Scrum, có thể điều chỉnh Sprint Backlog khi học được thông tin mới không? Giới hạn quan trọng là gì?
9. Vì sao việc tăng số PBI hoàn tất không tự chứng minh giá trị cho người dùng đã tăng?
10. Hãy nêu một tình huống phản hồi thực tế khiến nhóm **xóa hoặc hạ ưu tiên** một hạng mục mà vẫn tiến gần Product Goal hơn.

Trước mỗi lần chọn việc, hãy hỏi: **“Hạng mục này giúp đạt mục tiêu nào, vì sao nó đáng làm hơn những lựa chọn khác lúc này, và chúng ta sẽ thay đổi quyết định thế nào khi có bằng chứng mới?”** Trả lời được ba câu hỏi ấy là cách sử dụng backlog để hỗ trợ phát triển Agile thích ứng, giao giá trị tăng dần và cải tiến liên tục.
