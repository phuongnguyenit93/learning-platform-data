# Quản lý danh sách công việc và thứ tự ưu tiên trên phạm vi sản phẩm

> **Chương:** Phối hợp nhiều nhóm  
> **Học phần:** **AGILE_DEVELOPMENT** — hiểu giá trị và nguyên tắc Agile trong phát triển phần mềm thích ứng qua phản hồi sớm, giao sản phẩm tăng dần và cải tiến liên tục; thực hành user story, backlog, Scrum, Kanban, XP và đo lường dòng công việc để lựa chọn cách phối hợp phù hợp.

Một nền tảng đặt lịch tư vấn có ba nhóm phát triển. Nhóm A phụ trách giao diện đặt lịch, nhóm B xây nghiệp vụ giữ chỗ và thanh toán, nhóm C tích hợp lịch chuyên gia và thông báo. Mỗi nhóm đều có bảng backlog riêng, nhiều hạng mục được đánh dấu **High Priority** và báo cáo Sprint thành công. Nhưng khách hàng vẫn không thể đổi lịch vì giao diện đã xong, API đổi lịch còn chờ một hợp đồng tích hợp, còn quy tắc hoàn phí chưa được ai xác nhận. Cả ba nhóm đều bận, **giá trị sản phẩm vẫn đứng yên**.

Đây không chỉ là vấn đề công cụ quản lý công việc. Khi nhiều nhóm cùng phát triển **một sản phẩm**, việc quyết định thứ tự ưu tiên cần đặt ở **phạm vi sản phẩm**, không chỉ tối ưu từng bảng công việc. Nhóm phải có cách nhìn chung về **mục tiêu, nhu cầu người dùng, hạng mục mang giá trị, rủi ro, phụ thuộc và khả năng tạo ra phần mềm tích hợp được**.

Trong Scrum, **Product Backlog** là danh sách có thứ tự, đang tiến hóa, gồm những điều cần thiết để cải thiện sản phẩm và là nguồn công việc của Scrum Team. Khi nhiều Scrum Team cùng làm **một sản phẩm**, theo *Scrum Guide 2020* họ nên **chia sẻ cùng Product Goal, Product Backlog và Product Owner**. Tuy nhiên, quản lý backlog toàn sản phẩm không có nghĩa áp một mô hình chỉ huy giao task từ trên xuống: các nhóm vẫn cần quyền cộng tác kỹ thuật, làm rõ hạng mục và tự lập kế hoạch phù hợp với trách nhiệm của họ.

Bài học này hướng dẫn cách tạo **một bức tranh sản phẩm nhất quán**, chọn thứ tự công việc dựa trên tác động và bằng chứng, phát hiện phụ thuộc giữa nhóm, giữ chất lượng tích hợp, và cập nhật quyết định khi nhận phản hồi mới. Các thực hành có thể áp dụng trong Scrum, Kanban hoặc cách phối hợp lai, miễn là **không nhầm tính minh bạch với cơ chế kiểm soát vi mô**.

## 1. Kết quả học tập

Sau bài này, bạn có thể:

1. Giải thích sự khác nhau giữa **Product Goal, Product Backlog, roadmap, Sprint Backlog, kế hoạch kỹ thuật và danh sách công việc cấp tổ chức**.
2. Xác định **ranh giới một sản phẩm** để quyết định nhóm nào cùng dùng mục tiêu và backlog chung, tránh gộp các sản phẩm độc lập một cách máy móc.
3. Tổ chức Product Backlog theo **kết quả người dùng, năng lực và lát cắt chức năng nhỏ**, đồng thời hiển thị lỗi, rủi ro, công việc khám phá và nợ kỹ thuật.
4. Đưa công việc mới vào một **cơ chế intake/triage rõ ràng**, phân biệt nhu cầu sản phẩm với yêu cầu khẩn hoặc nghĩa vụ bắt buộc.
5. Thứ tự hóa công việc dựa trên **giá trị, chi phí trì hoãn, rủi ro, mức bất định, phụ thuộc, kích thước và năng lực**, dùng phương pháp điểm số như RICE hoặc WSJF với sự thận trọng.
6. Tạo bản đồ **phụ thuộc liên nhóm**, phân biệt phụ thuộc có thể loại bỏ với phụ thuộc nghiệp vụ thật và thiết kế lát cắt tích hợp sớm.
7. Hiểu trách nhiệm **Product Owner, Developers, Scrum Master** và các thỏa thuận phối hợp khi nhiều Scrum Team cùng tạo một Increment.
8. Dùng số đo **outcome, flow, chất lượng và dự báo** để kiểm tra quyết định ưu tiên, không đánh giá thành công bằng tỷ lệ bận rộn hay story points cộng dồn.
9. Thực hành một ví dụ ba nhóm cùng phát triển hệ thống đặt lịch, gồm điều chỉnh thứ tự khi bằng chứng hoặc năng lực thay đổi.

## 2. Vì sao nhiều backlog theo nhóm có thể làm mất hướng sản phẩm?

### 2.1. Tối ưu cục bộ khác tối ưu giá trị đầu cuối

Nhóm A có thể hoàn thành màn hình đổi lịch; nhóm B hoàn thành cập nhật bảng Appointment; nhóm C hoàn thành gửi SMS. Nhưng nếu khách chưa **đổi được một lịch hợp lệ** từ đầu tới cuối, các kết quả này chưa tự tạo ra chức năng dùng được.

| Chỉ số/cách nhìn cục bộ | Câu hỏi ở phạm vi sản phẩm |
| --- | --- |
| “Nhóm A đã hoàn thành 35 story points.” | Khách đã làm được tác vụ gì mới, ở môi trường nào? |
| “Nhóm B đóng 12 ticket.” | Những ticket đó có tạo ra lát cắt tích hợp và đạt chuẩn chất lượng không? |
| “Nhóm C không còn việc tồn.” | Phần nào đang chờ hợp đồng, dữ liệu hoặc quyết định nghiệp vụ từ các nhóm khác? |
| “Ba backlog đều có ưu tiên số 1.” | **Toàn sản phẩm** nên ưu tiên kết quả nào trước khi xét năng lực? |
| “Tính năng sắp xong 90%.” | Điều kiện còn thiếu để người dùng thực hiện tác vụ an toàn là gì? |

Một nhóm có thể sử dụng **board thực thi riêng** để nhìn việc của mình. Vấn đề xuất hiện khi những board đó trở thành **ba danh sách ưu tiên sản phẩm độc lập và xung đột**, khiến không ai chịu trách nhiệm nhìn mục tiêu chung.

### 2.2. Nhiều nhóm làm cùng sản phẩm tạo ba loại phụ thuộc

1. **Phụ thuộc nghiệp vụ:** Nút đổi lịch cần chính sách hủy và cách giữ giờ mới.
2. **Phụ thuộc kỹ thuật:** Giao diện cần API có hợp đồng rõ; dữ liệu/trạng thái phải tương thích.
3. **Phụ thuộc phối hợp:** Một nhóm chỉ có thể kiểm thử khi nhóm khác cung cấp môi trường, review hoặc dữ liệu.

Không phải tất cả phụ thuộc đều có hại. Một số phản ánh nghiệp vụ thực. Nhưng nếu mỗi nhóm chỉ thấy phần việc của mình, **điểm chờ nằm giữa các nhóm** dễ biến mất khỏi báo cáo.

### 2.3. Product Backlog chung không đòi mọi người làm cùng một công việc

Một Product Backlog chung thể hiện **sự minh bạch và thứ tự ưu tiên đối với những gì cần cải thiện sản phẩm**. Các nhóm có thể:

- Cùng làm các lát cắt khác nhau phục vụ một mục tiêu.
- Có bảng kỹ thuật và kế hoạch ngắn hạn riêng.
- Chia sẻ chuẩn tích hợp và Definition of Done khi dùng Scrum trên cùng sản phẩm.
- Chọn cách phối hợp để giảm chờ và kiểm thử sớm.

**Không nên sao chép một Product Backlog thành nhiều bản rồi đồng bộ thủ công mỗi tuần.** Nếu cần các chế độ xem theo nhóm, nên bảo đảm chúng là **những góc nhìn từ cùng nguồn quyết định sản phẩm**, không phải các hệ ưu tiên cạnh tranh.

## 3. Xác định phạm vi sản phẩm trước khi thống nhất backlog

### 3.1. “Cùng công ty” không đồng nghĩa “cùng sản phẩm”

Trước khi yêu cầu mọi nhóm dùng một backlog, cần xác định:

- **Người dùng/khách hàng và nhu cầu cốt lõi** là ai?
- Sản phẩm cung cấp **một đề xuất giá trị hoặc dịch vụ nhất quán** nào?
- Có **Product Goal** chung và cách kiểm tra tiến độ tới mục tiêu không?
- Các nhóm có cùng tạo ra một kết quả cần tích hợp hay vận hành cùng không?
- Một quyết định ưu tiên có cần **cân bằng lợi ích giữa các nhóm** cho cùng outcome không?
- Có ranh giới sản phẩm khác với mục tiêu, người dùng và quyền quyết định độc lập không?

Nếu nhóm xây ứng dụng đặt lịch khách hàng và nhóm khác vận hành một sản phẩm kế toán bán cho khách hàng khác, ép cả hai vào một Product Backlog có thể làm hỏng tính minh bạch. Ngược lại, chia một ứng dụng đặt lịch thành **ba sản phẩm chỉ vì có ba đội kỹ thuật** có thể che mất kết quả end-to-end.

### 3.2. Product Goal là mục tiêu, Product Backlog là lựa chọn đường đi

Ví dụ Product Goal:

> “Khách có thể tự đặt, kiểm tra và đổi lịch tư vấn hợp lệ mà không cần liên hệ tổng đài cho những trường hợp phổ biến.”

Đây là **đích giá trị**. Các lựa chọn để tiến tới đó có thể gồm:

- Làm rõ trạng thái Pending/Confirmed.
- Bảo vệ yêu cầu gửi lặp để không tạo trùng.
- Hiển thị giờ khả dụng theo múi giờ.
- Cho phép đổi lịch trong phạm vi chính sách.
- Cải thiện kiểm thử tích hợp để giao an toàn hơn.

**Product Backlog** sẽ tiến hóa về nội dung và thứ tự khi hiểu người dùng, rủi ro, nguồn lực thay đổi. Product Goal giúp nhóm **không nhảy giữa những hạng mục có vẻ hấp dẫn nhưng không tạo tiến bộ đáng kể**.

### 3.3. Khi một tổ chức có nhiều sản phẩm

| Cấp | Mục tiêu và quyết định | Không nên nhầm với |
| --- | --- | --- |
| **Chiến lược/tổ chức/portfolio** | Phân bổ đầu tư giữa các sản phẩm, mục tiêu kinh doanh rộng, ràng buộc. | Danh sách từng task code của các nhóm. |
| **Sản phẩm** | Product Goal, giá trị người dùng, Product Backlog có thứ tự, quyết định phạm vi. | Một bảng ticket cho từng chuyên môn. |
| **Nhóm phát triển** | Cách triển khai hạng mục, thiết kế kỹ thuật, kế hoạch làm việc, hỗ trợ tích hợp. | Quyền tự thay đổi mục tiêu giá trị sản phẩm mà không phối hợp. |
| **Vận hành và hỗ trợ** | Sự cố, chất lượng dịch vụ, khôi phục, nghĩa vụ đang có. | Một hàng chờ bình thường có thể trì hoãn mọi sự cố nghiêm trọng. |

Quản lý danh sách ở phạm vi sản phẩm không có nghĩa **mọi yêu cầu tổ chức đều phải đi qua một Product Owner duy nhất của cả công ty**. Quy mô và ranh giới quyết định khác nhau; cần xác định đúng sản phẩm và thẩm quyền.

### 3.4. Product Roadmap khác Product Backlog

**Roadmap** thường truyền đạt **hướng đi, các vấn đề cần giải quyết, outcome và những khoảng thời gian dự kiến**, với độ chắc chắn phù hợp. **Product Backlog** là danh sách các hạng mục cần thiết để cải thiện sản phẩm, có thứ tự và thường được làm rõ khác nhau theo vị trí.

Ví dụ roadmap có thể nói “cải thiện độ tin cậy khi đặt lịch” trong quý, còn Product Backlog có các item **idempotency**, **tra cứu trạng thái**, **đối soát timeout** và **quan sát lỗi**. Roadmap **không phải bản sao Gantt** liệt kê hàng trăm ticket với ngày chính xác giả.

## 4. Phân biệt các loại danh sách khi nhiều nhóm cùng làm

### 4.1. Bảng khái niệm

| Khái niệm | Mục đích | Ai quyết định chính? | Thay đổi theo thời gian? |
| --- | --- | --- | --- |
| **Product Goal** | Diễn đạt trạng thái tương lai của sản phẩm cần đạt. | Product Owner chịu trách nhiệm; được hình thành cùng bối cảnh sản phẩm. | Có thể đổi khi đạt mục tiêu hoặc chiến lược sản phẩm thay đổi phù hợp. |
| **Product Backlog** | Nguồn công việc có thứ tự để cải thiện **một sản phẩm**. | Product Owner chịu trách nhiệm nội dung, trật tự và tính minh bạch. | **Liên tục tiến hóa.** |
| **Product Backlog Item (PBI)** | Một điều cần cải thiện/biết/làm, được làm rõ đủ dùng. | Product Owner sắp thứ tự; Developers và stakeholder hỗ trợ refinement. | Được chia nhỏ, gộp, thêm, bỏ hoặc đổi thứ tự khi học. |
| **Sprint Goal** | Mục tiêu đơn nhất của một Sprint của Scrum Team. | Scrum Team xây dựng trong Sprint Planning. | Là cam kết, giữ trọng tâm và thương lượng phạm vi phù hợp. |
| **Sprint Backlog** | Sprint Goal, PBI được chọn và kế hoạch Developers thực hiện. | **Developers** tạo và thích ứng kế hoạch. | Cập nhật trong Sprint khi học thêm. |
| **Team board / task plan** | Quan sát tiến độ thực thi và công việc kỹ thuật. | Developers/nhóm sử dụng board theo workflow. | Thay đổi hằng ngày; có thể là góc nhìn từ PBI. |
| **Roadmap/forecast** | Truyền đạt định hướng, mốc giá trị và mức bất định. | Vai trò sản phẩm và stakeholder theo thẩm quyền. | Điều chỉnh theo bằng chứng, năng lực và rủi ro. |

**Quan trọng:** Trong Scrum, một **Sprint Backlog** không phải tên khác của Product Backlog. Khi nhiều nhóm cùng sản phẩm, họ có thể có **Sprint Backlog của từng Scrum Team**, đồng thời **chia sẻ Product Backlog của sản phẩm**.

### 4.2. Đừng dùng ba cấp danh sách như ba nguồn sự thật

~~~mermaid
flowchart TD
    G["Product Goal — kết quả chung"] --> PB["Product Backlog — một danh sách có thứ tự"]
    PB --> A["Những PBI nhóm A chọn/làm rõ"]
    PB --> B["Những PBI nhóm B chọn/làm rõ"]
    PB --> C["Những PBI nhóm C chọn/làm rõ"]
    A --> I["Increment tích hợp của sản phẩm"]
    B --> I
    C --> I
    I --> R["Phản hồi và kết quả thực tế"]
    R -. "Điều chỉnh thứ tự và nội dung" .-> PB
~~~

Sơ đồ diễn đạt **dòng giá trị**, không phải một quy trình cứng giao việc từ Product Owner tới từng cá nhân. Để tạo một Increment tích hợp, các nhóm còn phải cùng làm rõ phụ thuộc, ranh giới kỹ thuật, quyền truy cập và chuẩn chất lượng. Những PBI giao qua nhiều nhóm **không nên bị đánh dấu Done** chỉ vì một nhóm hoàn thành phần riêng.

### 4.3. Khi nào team backlog là hợp lý?

Một **team execution board** là hữu ích để hiển thị:

- Task xây API, giao diện, test và refactor phục vụ một PBI.
- Kết quả review, blocked và owner phối hợp.
- Hạn WIP và trạng thái của những phần việc nhóm đang kiểm soát.

Nó trở thành vấn đề khi nhóm tự cấp **priority 1** cho công việc không còn phù hợp Product Goal hoặc che sự thật “phần của nhóm đã Done nhưng kết quả sản phẩm chưa dùng được”.

**Cách phân biệt:** Có thể có nhiều **board**, nhưng cần xác định rõ **nguồn quyết định thứ tự sản phẩm**, cách liên kết task/PBI và trạng thái tích hợp thực.

## 5. Thiết kế Product Backlog dễ nhìn ở phạm vi sản phẩm

### 5.1. Thứ tự ưu tiên phải biểu diễn giá trị, không chỉ cấu trúc hệ thống

**Danh sách theo tầng kỹ thuật** dễ tạo phụ thuộc dây chuyền:

~~~text
1. Xây tất cả màn hình UI
2. Xây toàn bộ dịch vụ Booking
3. Xây toàn bộ tích hợp nhà cung cấp
4. Viết test tích hợp ở cuối
~~~

Ngay cả khi mỗi mục rất lớn có trạng thái “đang làm”, người dùng vẫn chưa có một chức năng nhỏ để thử.

**Danh sách có lát cắt giá trị** giúp nhóm kiểm chứng sớm hơn:

~~~text
Outcome: Khách biết chắc trạng thái đặt lịch
  - Xác nhận một giờ trống theo chính sách cơ bản.
  - Ngăn tạo hai lịch khi khách gửi lại cùng yêu cầu.
  - Hiển thị rõ Pending/Confirmed/Rejected.
  - Cho khách tra cứu trạng thái sau timeout.
  - Quan sát lỗi xác nhận và hỗ trợ đối soát.
~~~

Trong từng lát cắt vẫn cần UI, backend, storage, kiểm thử và tích hợp. Khác biệt nằm ở **hướng tổ chức quanh kết quả sử dụng được**, không phải chối bỏ chuyên môn kỹ thuật.

### 5.2. Cấu trúc cấp cao để dễ đọc, không tạo quan hệ cha–con bắt buộc

Một Product Backlog có thể có:

- **Product Goal hoặc outcome:** Điều mong muốn người dùng đạt được.
- **Opportunity/problem:** Nhu cầu hoặc điểm đau cần kiểm chứng.
- **Capability/feature:** Một năng lực sản phẩm phục vụ outcome.
- **PBI nhỏ:** Phần có thể làm rõ, xây và kiểm chứng trong thời gian ngắn.
- **Tasks/subtasks:** Công việc cụ thể thuộc kế hoạch thực thi, không nhất thiết quản lý như PBI độc lập.

Đây là **mô hình tổ chức thông tin tùy chọn**, không phải cấu trúc năm tầng Scrum Guide bắt buộc. Một tổ chức có thể dùng **epic, initiative, story mapping, opportunity solution tree** hoặc cách khác; điều quan trọng là **trật tự ở cấp sản phẩm vẫn rõ, không trùng lặp và có liên hệ giá trị**.

### 5.3. Trường thông tin tối thiểu cho một PBI

| Trường | Câu hỏi cần trả lời | Ví dụ |
| --- | --- | --- |
| **Tên và kết quả** | Người dùng hay hệ thống nhận được hành vi gì? | “Tra cứu trạng thái đã xử lý của yêu cầu đặt lịch”. |
| **Giá trị/rủi ro** | Vì sao đáng làm? | Giảm khách gửi lặp và gọi tổng đài. |
| **Đối tượng/bối cảnh** | Ai, dùng khi nào? | Khách đặt lịch trên mobile khi mạng chậm. |
| **Tiêu chí chấp nhận** | Khi nào coi hành vi đúng? | Lần gửi lặp không tạo lịch thứ hai; trạng thái có thẩm quyền rõ. |
| **Bằng chứng/giả định** | Điều gì đã biết, chưa biết? | Có phản ánh hỗ trợ, chưa rõ tần suất trên toàn tập. |
| **Phụ thuộc** | Cần hợp đồng/quy tắc/khả năng nào? | Kết quả backend và quyền tra cứu. |
| **Độ lớn/rủi ro** | Có thể hoàn tất và kiểm chứng trong một lát cắt không? | Cần thử API đối tác trước khi cam kết chi tiết. |
| **Trạng thái minh bạch** | Đang cần làm rõ, đã chọn, bị chặn hay đã đạt Done? | Test retry và hợp đồng đối tác chưa sẵn. |

Không phải mọi PBI xa trong tương lai cần tất cả các trường ở độ chi tiết như PBI sắp được làm. **Refinement là quá trình tiến hóa**, không phải yêu cầu điền mọi ô cho hàng trăm mục trước khi giao giá trị.

### 5.4. “Một nguồn sự thật” không nhất thiết là một công cụ

Trong tổ chức lớn, dữ liệu có thể nằm ở hệ thống hỗ trợ, tài liệu khám phá, board kỹ thuật và công cụ product analytics. Điều cần thống nhất là:

1. **Ai chịu trách nhiệm thứ tự ở phạm vi sản phẩm?**
2. **PBI nào là đại diện chuẩn của nhu cầu cần làm?**
3. **Các bản sao hoặc góc nhìn được liên kết và cập nhật thế nào?**
4. **Khi nguồn dữ liệu xung đột, quy tắc giải quyết ra sao?**

Việc mua một công cụ mới không tự giải quyết được bất đồng giữa ba nhóm về “điều gì đáng làm trước”.

## 6. Cơ chế nhận công việc mới và triage trên phạm vi sản phẩm

Một Product Backlog chung chỉ hữu ích nếu **công việc mới được làm rõ, tránh trùng và đặt vào đúng đường quyết định**. Nếu sales, vận hành, pháp chế và mỗi nhóm kỹ thuật tự giao trực tiếp ticket ưu tiên cao, năng lực sản phẩm sẽ bị chia nhỏ.

### 6.1. Nguồn phát sinh

| Nguồn | Ví dụ | Điều cần làm rõ |
| --- | --- | --- |
| **Người dùng/khách hàng** | “Không biết yêu cầu đặt lịch đã nhận chưa.” | Vấn đề thực, nhóm bị ảnh hưởng, bằng chứng. |
| **Stakeholder sản phẩm** | “Cần SMS xác nhận cho mọi khách.” | Mục tiêu và giá trị, chi phí, giải pháp khác. |
| **Chất lượng kỹ thuật** | Lỗi tạo lịch trùng do retry. | Mức nghiêm trọng, sự cố hiện tại, phòng ngừa và kiểm chứng. |
| **Vận hành/hỗ trợ** | API đối tác timeout thường xuyên. | Phạm vi ảnh hưởng, logs, ngưỡng an toàn và khả năng ứng cứu. |
| **Khám phá (discovery)** | Chưa biết nhà cung cấp có idempotency không. | Câu hỏi, quyết định bị chặn, timebox. |
| **Nợ kỹ thuật/bảo mật** | Thay trạng thái khiến nhiều test hỏng, thư viện có lỗ hổng. | Rủi ro, chi phí trì hoãn, điều kiện tuân thủ. |
| **Nghĩa vụ hợp đồng/quy định** | Cần thay đổi báo cáo bắt buộc đúng hạn. | Thẩm quyền xác nhận, hạn, phạm vi tối thiểu và rủi ro. |

**Không nên ép tất cả thành một mẫu user story “Là người dùng…”**. Lỗi dữ liệu, công việc tuân thủ, nâng cấp bảo mật và spike kỹ thuật có thể cần cách diễn đạt khác, nhưng vẫn phải **hiển thị chi phí năng lực và ảnh hưởng tới mục tiêu**.

### 6.2. Một quy trình intake/triage thực dụng

~~~mermaid
flowchart TD
    A["Yêu cầu/tín hiệu mới"] --> B["Ghi nguồn, bối cảnh, bằng chứng"]
    B --> C{"Có rủi ro khẩn cấp đang gây thiệt hại?"}
    C -->|Có| D["Ứng cứu/triage theo chính sách vận hành"]
    C -->|Không| E["Phân biệt vấn đề, giải pháp và giả định"]
    D --> F["Khắc phục, đối soát và đưa follow-up thích hợp vào backlog"]
    E --> G{"Đã đủ hiểu để so ưu tiên?"}
    G -->|Chưa| H["Discovery/spike có giới hạn"]
    G -->|Rồi| I["Product Owner sắp thứ tự dựa trên giá trị/rủi ro"]
    H --> I
    F --> I
    I --> J["Refinement, cắt lát và phối hợp năng lực"]
    J --> K["Tạo Increment/đưa kết quả vào sử dụng"]
    K --> L["Quan sát và cập nhật Product Backlog"]
~~~

Không phải mọi ý tưởng đều cần thêm thành PBI. Có thể **trả lời một câu hỏi, bỏ một đề xuất không có giá trị, hợp nhất các phản ánh trùng, hoặc lưu một giả thuyết để xem lại**. Mục tiêu của intake là **chọn đúng việc**, không làm tăng lượng ticket.

### 6.3. Phân biệt ưu tiên sản phẩm với luồng sự cố

Nếu production tạo lịch trùng hoặc làm lộ dữ liệu, cần kích hoạt **quy trình ứng cứu và giảm thiệt hại** theo chính sách. Product Owner và Developers phải biết công việc này ảnh hưởng năng lực/dự báo; nhưng không nên chờ buổi backlog refinement tuần sau mới xử lý một sự cố khẩn.

Sau ứng cứu, lỗi gốc rễ, kiểm thử hồi quy, cải thiện quan sát và workarounds lâu dài có thể trở thành PBI/công việc kỹ thuật phù hợp, được cân bằng với mục tiêu sản phẩm.

### 6.4. Một mẫu ghi nhận nhu cầu mới

~~~yaml
source: "Phản hồi người dùng qua tổng đài"
problem: "Khách không biết yêu cầu đặt lịch đã được xác nhận chưa"
user_segment: "Khách dùng điện thoại với mạng không ổn định"
observed_evidence:
  - "Một số cuộc gọi hỏi trạng thái"
  - "Có sự kiện gửi lại cùng tác vụ"
unknowns:
  - "Tỷ lệ gặp vấn đề trên toàn tập"
  - "Khả năng truy vấn lại trạng thái từ API đối tác"
risk: "Có thể tạo dữ liệu trùng nếu backend không bảo vệ retry"
candidate_outcome: "Khách biết trạng thái mà không phải gửi yêu cầu mới"
decision_needed: "Sửa an toàn trước, sau đó chọn lát cắt UI/đối soát"
owner: "Product Owner phối hợp Developers và người chịu trách nhiệm vận hành"
~~~

Đây là **mẫu minh họa**, không phải đặc tả công cụ hoặc dữ liệu đã xác minh. Những phản ánh có thông tin cá nhân phải được xử lý theo chính sách quyền riêng tư và chỉ đưa nội dung tối thiểu cần thiết vào backlog.

## 7. Refinement ở phạm vi sản phẩm: đủ rõ để nhiều nhóm cùng hiểu

**Product Backlog refinement** là hoạt động liên tục chia nhỏ và làm rõ các hạng mục để có thêm chi tiết, thứ tự và kích thước phù hợp. Trong Scrum, đây **không phải một sự kiện chính thức riêng** với timebox bắt buộc. Refinement cần phục vụ **những quyết định sắp tới**, chứ không phải cố đặc tả hoàn hảo toàn bộ tương lai.

### 7.1. Những câu hỏi tối thiểu trước khi chọn PBI

1. **Ai nhận giá trị hoặc tránh được rủi ro?** Khách đặt lịch, bộ phận hỗ trợ hay hệ thống vận hành?
2. **Hành vi có thể kiểm chứng là gì?** Tạo lịch hợp lệ, xem giờ trống hoặc tra cứu trạng thái?
3. **Điều gì vẫn chưa biết?** Chính sách hủy, hợp đồng API, khả năng retry?
4. **Phải đúng những bất biến nào?** Không có hai lịch đã xác nhận xung đột, không làm lộ dữ liệu?
5. **Có thể làm thành lát cắt nhỏ hơn không?** Dùng một loại lịch hoặc tình huống cơ bản trước?
6. **Cần phối hợp nhóm nào?** Ai hiểu domain, API, test và việc phát hành?
7. **Làm sao biết item đã hoàn tất?** Hành vi tích hợp và chất lượng đạt chuẩn, không chỉ phần code một đội.

### 7.2. Chia theo luồng người dùng, không cắt ngang ở từng tầng

Giả sử hạng mục ban đầu là **“Cho khách tự đổi mọi loại lịch”**. Nó có thể bao gồm quá nhiều trường hợp: đổi có hoàn phí, đổi sát giờ, phiên nhiều chuyên gia, đối tác chỉ hỗ trợ hủy/tạo lại và hàng loạt trạng thái lỗi.

**Cách chia thành lát cắt giá trị:**

| Lát cắt | Phạm vi minh họa | Bằng chứng hoàn tất |
| --- | --- | --- |
| **S1 — Xem khả năng đổi** | Lịch Confirmed, không phí, trong thời hạn cho phép. | Khách biết có thể đổi hay không và lý do rõ. |
| **S2 — Đổi giờ cơ bản** | Một chuyên gia, một chỗ, giờ thay thế còn trống. | Khách đổi thành công; không sinh lịch xung đột. |
| **S3 — Xử lý gửi lặp** | Retry cùng yêu cầu đổi lịch. | Không đổi hai lần hoặc mất lịch ngoài ý muốn. |
| **S4 — Xử lý đối tác timeout** | Không rõ kết quả đổi sau timeout. | Có trạng thái và cơ chế đối soát phù hợp. |
| **S5 — Trường hợp có phí/hoàn tiền** | Quy tắc tài chính được xác minh. | Phí và kết quả giao dịch đúng, kiểm chứng đầy đủ. |

Từng lát cắt có thể yêu cầu làm việc ở **UI, domain, persistence và integration**. Cần đánh giá thứ tự theo an toàn và phụ thuộc: **không nên phát hành S2 cho khách thật khi chống trùng và xử lý lỗi trọng yếu chưa đáp ứng điều kiện chất lượng**. Các mục trong bảng là lát cắt học tập, không mặc định đủ điều kiện release độc lập trong mọi hệ thống.

### 7.3. Story mapping để nhìn hành trình toàn sản phẩm

~~~text
Hành trình khách:
Tìm chuyên gia -> Xem giờ -> Đặt lịch -> Kiểm tra kết quả -> Đổi/hủy
                    |           |               |               |
                 Xem múi giờ  Yêu cầu hợp lệ  Hiển thị Pending  Xem chính sách
                 Xem ngày nghỉ Chống gửi lặp  Tra cứu trạng thái Đổi giờ cơ bản
                 Lọc dịch vụ  Đối tác xác nhận Đối soát timeout  Hoàn phí
~~~

Story map giúp nhóm thấy **nơi giá trị đầu-cuối bị đứt**. Nó không thay thế thứ tự cụ thể của Product Backlog; có thể dùng để thảo luận **các lát cắt phát hành/cơ hội học** rồi chuyển thành các PBI có thứ tự.

### 7.4. Tạo hợp đồng sớm thay vì chờ từng nhóm làm xong

Một PBI cần cả UI và Booking API có thể bị chậm vì hai nhóm ngầm hiểu khác nghĩa của **“success”**. Trong refinement liên nhóm, nên làm rõ:

- **Success** là request đã được chấp nhận hay lịch đã Confirmed?
- **Pending/Unknown** có ý nghĩa gì?
- Khi retry, trả lại kết quả cũ hay tạo lệnh mới?
- Lỗi nào là lỗi nghiệp vụ, lỗi nào là lỗi hạ tầng?
- Ai chịu trách nhiệm giữ bất biến chống trùng tại điểm ghi?
- Kiểm thử hợp đồng và tích hợp nằm trong tiêu chí hoàn tất nào?

**Làm rõ hợp đồng trước khi chia task** giúp tránh ba nhóm làm ba cách diễn giải rồi tích hợp thất bại.

### 7.5. Refinement không phải hứa tất cả hạng mục sẽ xong đúng ngày

Hạng mục càng xa trong danh sách càng có nhiều bất định. Không cần ước lượng chính xác và viết đầy đủ acceptance criteria của hàng trăm mục **có thể không bao giờ được làm**.

Nên:

1. Giữ phần xa ở mức **mục tiêu, vấn đề, giả định và rủi ro**.
2. Làm rõ phần sắp chọn để Developers có thể dự báo và phối hợp.
3. Chia nhỏ khi gặp phụ thuộc hoặc kích thước quá lớn.
4. Xóa/gộp các PBI không còn phù hợp.
5. Cập nhật thứ tự khi Product Goal hoặc bằng chứng thay đổi.

## 8. Thứ tự ưu tiên ở phạm vi sản phẩm: từ giá trị tới điều kiện giao

### 8.1. “Ưu tiên cao” chỉ có nghĩa khi có thứ tự và đánh đổi

Nếu mọi nhóm đều có mười PBI **Priority: High**, không ai biết **việc nào nên hoàn tất trước khi có xung đột năng lực**. Product Backlog có thứ tự giúp Product Owner giải thích vì sao hạng mục A đứng trước B trong bối cảnh mục tiêu và năng lực hiện tại.

**Lưu ý:** Thứ tự không phải một hàng đợi thực thi tuyệt đối cho mọi người. Một PBI ưu tiên cao nhưng đang chờ API/thiết kế hoặc chưa thể làm an toàn có thể dẫn tới:

- Làm một **spike có timebox** để giảm bất định.
- Xử lý một **enabler/phụ thuộc** cần thiết.
- Chọn PBI khác phù hợp năng lực còn lại trong khi không che rủi ro.
- Điều chỉnh phạm vi/forecast với stakeholder.

Không nên làm “feature dễ đóng” chỉ để báo tiến độ khi mục tiêu sản phẩm quan trọng đang bị chặn mà không ai tháo gỡ.

### 8.2. Các tiêu chí cân bằng

| Tiêu chí | Câu hỏi ưu tiên | Ví dụ |
| --- | --- | --- |
| **Giá trị/Outcome** | Khách nhận lợi ích cụ thể gì nếu xong? | Tra cứu trạng thái giúp giảm bất định. |
| **Rủi ro và mức nghiêm trọng** | Điều gì có thể gây thiệt hại nếu trì hoãn? | Lỗi retry có thể tạo lịch trùng. |
| **Cost of Delay** | Mất gì nếu giao muộn một khoảng thời gian? | Mỗi tuần khách phải nhờ tổng đài nhiều hơn. |
| **Bằng chứng và bất định** | Có dữ liệu nào, giả định nào chưa kiểm chứng? | Chưa biết API đối tác hỗ trợ idempotency. |
| **Kích thước/công sức** | Chi phí cơ hội và khả năng chia lát cắt? | Feature cần ba nhóm nhiều tuần có thể tách thử một trường hợp. |
| **Phụ thuộc/mở khóa** | Việc này có giúp hạng mục giá trị khác hoàn tất không? | Hợp đồng trạng thái giúp UI và thông báo cùng làm. |
| **Thời hạn/nghĩa vụ** | Có hạn thực sự hay chỉ ngày mong muốn? | Yêu cầu bảo mật phải đáp ứng trước một mốc. |
| **Sự phù hợp chiến lược** | Có tiến tới Product Goal hiện tại không? | Thêm hiệu ứng hình ảnh chưa chắc giúp đặt lịch thành công. |
| **Năng lực và tải hiện tại** | Có đội/người/phụ thuộc đủ thực hiện an toàn không? | Partner integration đang là nút thắt. |

**Không có một công thức tự động quyết định mọi thứ.** Product Owner cần làm rõ **lý do, giả định, thẩm quyền và đánh đổi**, thay vì lấy số điểm làm mệnh lệnh không thể chất vấn.

### 8.3. Giá trị là điều đạt được, không phải số người yêu cầu

Ví dụ:

- Một đại diện sales muốn thêm SMS xác nhận.
- Nhiều khách mới gặp lỗi không hiểu Pending.
- Developers phát hiện idempotency chưa được bảo vệ đúng.

Lựa chọn hợp lý có thể là **ưu tiên sửa bất biến trước**, rồi cải thiện trạng thái và đo tác động, còn SMS cần thêm bằng chứng. Đây không phải do ai nói lớn nhất hay nhỏ nhất, mà vì **rủi ro dữ liệu và khả năng hoàn tất tác vụ** có tác động nền tảng.

### 8.4. Rủi ro cao nhưng chưa biết giải pháp: ưu tiên học

Nếu chưa rõ một nhà cung cấp có trả trạng thái sau timeout không, cam kết xây đầy đủ tính năng đổi lịch cho mọi trường hợp có thể tạo rework lớn. Một **discovery/spike ngắn** với câu hỏi và tiêu chí kết thúc rõ có thể đứng trước phần phát triển lớn.

**Ví dụ:**

~~~text
Câu hỏi: API đối tác có nhận diện gửi lại bằng idempotency key không?
Quyết định bị chặn: thiết kế an toàn cho thao tác đổi lịch.
Timebox: 2 ngày làm việc trong sandbox.
Bằng chứng cần: hợp đồng API, thử gửi trùng, timeout và query trạng thái.
Đầu ra: phương án, giới hạn, rủi ro chưa giải quyết và PBI cần thay đổi.
Không thuộc phạm vi: xây toàn bộ chức năng đổi lịch production.
~~~

Spike là **công việc khám phá có giới hạn**, không phải đường vòng để đưa tính năng chưa đạt chất lượng vào production.

## 9. Các phương pháp hỗ trợ ưu tiên: RICE, WSJF và Cost of Delay

Điểm số có thể hữu ích để **làm lộ giả định và so các lựa chọn cùng loại**, nhưng **không biến các ước lượng chủ quan thành sự thật chính xác**. Đặc biệt, các lỗi về an toàn và nghĩa vụ bắt buộc cần xử lý bằng chính sách phù hợp, không chỉ dựa vào điểm RICE/WSJF.

### 9.1. RICE là công cụ suy nghĩ, không phải quyền quyết định

**RICE** thường gồm:

- **Reach:** Số người/tác vụ có khả năng được ảnh hưởng trong cùng cửa sổ thời gian.
- **Impact:** Mức thay đổi kết quả cho từng đối tượng được tiếp cận (thường là thang tương đối).
- **Confidence:** Mức độ tin cậy vào ước lượng/giả thuyết.
- **Effort:** Công sức thực hiện, tính trên cùng đơn vị ước lượng.

Một công thức tham khảo:

\[
\text{RICE score}=\frac{\text{Reach}\times\text{Impact}\times\text{Confidence}}{\text{Effort}}
\]

**Ví dụ hoàn toàn giả định**, Reach tính theo **tài khoản chịu tác động trong một quý**, Effort tính bằng **person-month**, Confidence dạng 0–1, Impact là thang tương đối đã thống nhất:

| Hạng mục | Reach/quý | Impact | Confidence | Effort | Điểm minh họa |
| --- | ---: | ---: | ---: | ---: | ---: |
| **A — Làm rõ trạng thái Pending** | 2.000 | 1,5 | 0,8 | 2 | 1.200 |
| **B — Thêm SMS nhắc lịch** | 1.500 | 1,0 | 0,4 | 3 | 200 |
| **C — Tăng tùy biến màu giao diện** | 1.000 | 0,5 | 0,5 | 1 | 250 |

Kiểm tra phép tính: \(A=2000\times1{,}5\times0{,}8/2=1200\); \(B=1500\times1\times0{,}4/3=200\); \(C=1000\times0{,}5\times0{,}5/1=250\).

Trong ví dụ này A trông đáng ưu tiên hơn B/C. Nhưng **không thể so A với lỗi tạo trùng đã xác minh chỉ bằng điểm RICE**: an toàn dữ liệu là điều kiện phải bảo vệ, không phải một feature trang trí với Reach thấp.

### 9.2. Cost of Delay

**Cost of Delay (CoD)** hỏi: *Mỗi đơn vị thời gian trì hoãn khiến chúng ta mất hoặc chịu thêm điều gì?*

Có thể là:

- Doanh thu/cơ hội bị mất.
- Chi phí hỗ trợ hoặc xử lý thủ công tiếp tục tăng.
- Thiệt hại do rủi ro và giảm uy tín.
- Mất khả năng học từ phản hồi đúng thời điểm.
- Vi phạm mốc bắt buộc có hậu quả thực tế.

CoD **không tự nhiên dễ định lượng**. Nếu không đủ dữ liệu để quy ra tiền, nhóm có thể dùng so sánh tương đối có căn cứ. Không gắn một con số USD giả lên yêu cầu chỉ để trông khoa học.

### 9.3. WSJF — cân nhắc CoD so với độ lớn

Một cách dùng phổ biến của **Weighted Shortest Job First (WSJF)** là:

\[
\text{WSJF}=\frac{\text{Cost of Delay tương đối}}{\text{Job Size tương đối}}
\]

Ở một cách phân rã thường gặp trong SAFe, CoD tương đối có thể xem từ **business value + time criticality + risk reduction/opportunity enablement**. Đây là **một kỹ thuật ưu tiên tùy chọn**, không phải quy tắc bắt buộc của Scrum Guide.

**Ví dụ số minh họa**, tất cả số điểm theo một thang đánh giá tương đối:

| Hạng mục | Business value | Time criticality | Risk reduction / enablement | CoD tổng | Job size | WSJF |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| **P1 — Tra cứu trạng thái đặt lịch** | 8 | 5 | 3 | 16 | 4 | **4,0** |
| **P2 — Khám phá API retry** | 3 | 5 | 8 | 16 | 2 | **8,0** |
| **P3 — Thêm SMS nhắc lịch** | 5 | 2 | 1 | 8 | 5 | **1,6** |

Phép tính: P1 \(16/4=4\), P2 \(16/2=8\), P3 \(8/5=1{,}6\).

P2 có thể là một **bước học nhỏ mở khóa quyết định quan trọng**. Nhưng nếu nó chỉ giúp quyết định có nên làm P1 thì cần mô tả liên hệ đó; **không nên biến điểm WSJF thành kết luận P2 tạo gấp đôi giá trị P1 cho khách hàng**.

### 9.4. Bẫy khi dùng điểm số

1. **Độ chính xác giả:** “Confidence = 93%” do ai đó đoán.
2. **Đổi thang giữa nhóm:** Nhóm A cho Impact 10 khi “hữu ích”, nhóm B cho Impact 10 khi “an toàn sinh mạng”.
3. **Bỏ rủi ro tích hợp:** Job size của mỗi nhóm có vẻ nhỏ nhưng dependency khiến thời gian giao dài.
4. **Tối ưu mục dễ đóng:** Chia item thành ticket vụn để tăng điểm WSJF.
5. **Bỏ qua chi phí cơ hội:** Một việc yêu cầu chuyên gia duy nhất có thể chặn mục giá trị cao hơn.
6. **Che yêu cầu bắt buộc:** Một lỗi bảo mật bị điểm thấp vì Reach hiện tại nhỏ.

Hãy dùng bảng điểm để hỏi **“giả định nào giải thích sự khác biệt?”**, rồi quyết định dựa trên mục tiêu, rủi ro và khả năng thực hiện có kiểm chứng.

### 9.5. Không cần chọn đúng một “công thức ưu tiên” cho mọi loại công việc

| Loại công việc | Cách ra quyết định thường hợp lý |
| --- | --- |
| **Lỗi production nghiêm trọng** | Chính sách incident/triage, mức ảnh hưởng và nghĩa vụ an toàn. |
| **Feature cạnh tranh giá trị** | Giá trị người dùng, CoD, bằng chứng, effort và Product Goal. |
| **Discovery/spike** | Mức bất định, quyết định bị chặn, chi phí khảo sát và thời điểm cần kết quả. |
| **Nợ kỹ thuật** | Rủi ro, số lần gây chậm, chi phí thay đổi và feature được mở khóa. |
| **Việc tuân thủ** | Nghĩa vụ, hạn thật và mức rủi ro; làm rõ phạm vi tối thiểu an toàn. |
| **Cải thiện vận hành** | Độ tin cậy, tần suất sự cố, thời gian phục hồi và chi phí duy trì. |

Một Product Backlog có thể chứa nhiều loại việc. Điều quan trọng là **quyết định phối hợp và năng lực chung được minh bạch**, không bắt mọi thứ thành “feature có Reach”.

## 10. Cân bằng năng lực, phụ thuộc và mức bất định

### 10.1. Năng lực không phải tổng story points của nhiều nhóm

Story points (nếu nhóm dùng) thường là **đơn vị ước lượng tương đối riêng của từng nhóm**. Nhóm A hoàn thành 20 points và nhóm B hoàn thành 30 points **không thể kết luận** cả sản phẩm có năng lực 50 points tương đương. Thang ước lượng, loại việc và cách đo khác nhau.

Để dự báo ở cấp sản phẩm, có thể xem:

- **Throughput lịch sử** của những hạng mục có định nghĩa tương đồng.
- **Cycle time và phân bố thời gian** tới điểm hoàn tất có ý nghĩa.
- **Năng lực chuyên môn giới hạn** (ví dụ chỉ một nhóm nắm hợp đồng API đối tác).
- **Sự cố, hỗ trợ và công việc bắt buộc** thường xuyên chiếm năng lực.
- **Phụ thuộc chéo**, thứ tự học và thời gian tích hợp.
- **Mức bất định** của hạng mục tương lai.

Không gán ngày phát hành chính xác chỉ từ tổng điểm giả định hoặc tỷ lệ bận rộn 100%.

### 10.2. Ví dụ năng lực ba nhóm không đồng nhất

Giả sử ba nhóm có lịch làm việc trong bốn tuần. Dữ liệu giả định:

| Nhóm | Năng lực chính | Cam kết/ngắt việc đã biết | Rủi ro cần lưu ý |
| --- | --- | --- | --- |
| **A — Trải nghiệm** | UI, khả năng sử dụng, accessibility. | Hỗ trợ các thay đổi nhỏ đang phát hành. | Có thể chờ hợp đồng trạng thái từ B. |
| **B — Booking domain** | Bất biến đặt trùng, giao dịch, trạng thái. | Một phần thời gian dành lỗi production. | Là điểm tập trung của nhiều PBI ưu tiên. |
| **C — Integration** | Đối tác, đồng bộ, notifications. | Đối tác có lịch sandbox bảo trì. | Hợp đồng retry chưa chắc chắn. |

Một quyết định có thể là để **C khảo sát API retry sớm**, **B xây test bảo vệ bất biến**, **A nghiên cứu trạng thái Pending trên prototype**. Sau khi bằng chứng đủ và hợp đồng rõ, nhóm có thể chọn **một lát cắt tích hợp** thay vì để A xây hết giao diện đổi lịch trong lúc B/C chưa thể đáp ứng.

**Không ngụ ý mỗi nhóm phải bận 100%.** Khi B là nút thắt, đưa thêm nhiều việc vào B có thể tăng WIP mà không tăng số chức năng được giao. Năng lực trống ở A có thể dùng để giúp kiểm thử, discovery, refactor an toàn hoặc cải tiến độc lập có giá trị.

### 10.3. Dự trù chất lượng nhưng tránh quota máy móc

Product Backlog có thể chứa việc bảo mật, nợ kỹ thuật và độ tin cậy. Nhóm có thể dùng một **ngân sách năng lực dự kiến** cho hỗ trợ/vận hành và cải tiến kỹ thuật nếu lịch sử cho thấy điều đó cần thiết. Nhưng không nên tuyên bố mọi đội bắt buộc “20% nợ kỹ thuật, 60% feature, 20% bug” bất kể thực tế.

Ví dụ kỳ có sự cố nghiêm trọng cần tăng năng lực khắc phục; kỳ khác có ít lỗi và một cơ hội thị trường rõ, có thể dành nhiều năng lực hơn cho feature. **Tỷ lệ là giả định lập kế hoạch có thể điều chỉnh**, không phải giá trị Agile cố định.

### 10.4. Kiểm tra tính sẵn sàng trước khi chọn nhiều PBI song song

Một PBI đòi hai nhóm có thể cần lịch phối hợp trước:

| PBI | Nhóm liên quan | Đầu vào quan trọng | Cách giảm chờ |
| --- | --- | --- | --- |
| Hiển thị Pending | A, B | Định nghĩa trạng thái và API | Đồng xây ví dụ/contract trước, thử UI qua stub có test. |
| Chống retry tạo trùng | B, C | Khả năng API đối tác, cơ chế ghi nhất quán | Spike sớm và test cạnh tranh trên sandbox. |
| Thông báo xác nhận | B, C | Sự kiện/trạng thái đã commit | Hợp đồng sự kiện và chính sách retry thông báo. |
| Đổi lịch cơ bản | A, B, C | Quy tắc đổi, giữ chỗ, timeout | Chia trường hợp đơn giản và test đầu-cuối sớm. |

Mở bốn PBI đồng thời khi cùng cần B có thể khiến **tất cả đều chờ**. Thứ tự backlog nên giúp nhóm **hoàn tất lát cắt có giá trị**, không tối đa hóa số hạng mục Started.

### 10.5. Forecast có mức bất định

Thay vì hứa “toàn bộ chức năng đổi lịch có mặt sau đúng ba Sprint” từ ước lượng sơ bộ, có thể truyền đạt:

> “Luồng đổi lịch cơ bản phụ thuộc kết quả thử API retry và quy tắc giữ chỗ. Sau khi chốt hợp đồng và hoàn thành lát cắt tích hợp đầu tiên, nhóm sẽ cập nhật phạm vi và dự báo bằng dữ liệu throughput/cycle time hiện có. Những trường hợp có hoàn phí và đối tác timeout chưa đủ căn cứ để cam kết cùng mốc.”

Lời nói này **không né trách nhiệm**; nó công khai **cái gì chắc, cái gì chưa và quyết định tiếp theo dựa vào điều gì**.

## 11. Quản lý phụ thuộc liên nhóm bằng cách giảm, làm rõ và kiểm chứng

### 11.1. Một bản đồ phụ thuộc sản phẩm

Giả sử Product Goal là hỗ trợ **đổi lịch an toàn**. Một số công việc liên quan:

~~~mermaid
flowchart LR
    RULE["P1: Chính sách đổi lịch"] --> DOMAIN["P3: Thao tác đổi hợp lệ"]
    API["P2: Khảo sát API đối tác"] --> DOMAIN
    API --> REC["P4: Đối soát khi timeout"]
    DOMAIN --> UI["P5: Luồng UI đổi lịch"]
    DOMAIN --> NOTIF["P6: Thông báo sau đổi"]
    REC --> E2E["Lát cắt tích hợp đủ điều kiện giao"]
    UI --> E2E
    NOTIF --> E2E
    DOMAIN --> E2E
~~~

Sơ đồ chỉ minh họa: **mũi tên A → B nghĩa là thông tin hoặc hành vi từ A cần thiết để B hoàn tất theo phạm vi chọn**, không nhất thiết A phải xong 100% mọi phần trước B mới được bắt đầu.

Nhóm có thể cùng viết hợp đồng và kiểm thử sớm để làm song song **những phần thực sự độc lập**, nhưng không nên giả rằng dùng một stub đẹp chứng minh luồng production hoạt động.

### 11.2. Bốn cách xử lý một phụ thuộc

| Cách | Khi nào phù hợp | Ví dụ |
| --- | --- | --- |
| **Loại bỏ bằng ranh giới rõ** | Phụ thuộc do chi tiết kỹ thuật rò rỉ hoặc ownership mơ hồ. | UI không cần biết SDK lịch đối tác, chỉ cần hợp đồng Booking có nghĩa. |
| **Thu nhỏ bằng cắt lát** | Chỉ một phần hành vi cần phối hợp để tạo giá trị đầu tiên. | Đổi lịch cơ bản không có phí trước khi hỗ trợ nhiều chính sách phức tạp. |
| **Làm rõ bằng hợp đồng/contract tests** | Có API hoặc dữ liệu giao tiếp ổn định cần cùng hiểu. | Pending/Confirmed/Unknown và mã lỗi có tiêu chí kiểm thử. |
| **Điều phối theo thời điểm** | Phụ thuộc nghiệp vụ thật hoặc nguồn lực giới hạn không thể bỏ ngay. | Workshop quy tắc hoàn tiền trước khi xây phần giao dịch. |

**Mục tiêu không phải loại bỏ mọi phụ thuộc.** Một invariant chống đặt trùng phải có cơ chế bảo đảm thực; không thể “phân tán phụ thuộc” để bỏ qua transaction hay đối soát.

### 11.3. Dependency board khác Product Backlog

Có thể bổ sung một **dependency view** cho những PBI gần:

| Phụ thuộc | Phục vụ PBI nào | Người phối hợp | Tình trạng | Hướng giải quyết |
| --- | --- | --- | --- | --- |
| Ngữ nghĩa Pending/Confirmed | P1, P5, P6 | A và B cùng chuyên gia miền | Cần làm rõ | Ví dụ nghiệp vụ + contract test. |
| Retry API đối tác | P2, P3, P4 | B và C | Chưa kiểm chứng | Spike sandbox có timebox. |
| Tài khoản môi trường tích hợp | P3, P4 | C và vận hành | Bị chặn | Xác định quyền/đầu mối và thời điểm sẵn sàng. |
| Test concurrent booking | P3, E2E | B và người kiểm thử | Đang thiết kế | Test với transaction/ràng buộc thật. |

**Không tạo một “backlog phụ thuộc” tách rời khiến ai cũng tưởng nó đã được ưu tiên độc lập.** Liên kết phụ thuộc với PBI sản phẩm và đưa chi phí/độ trễ vào quyết định thứ tự.

### 11.4. Một cuộc họp phối hợp không thay được thiết kế ranh giới

Thêm một cuộc họp liên nhóm hằng ngày có thể giúp phát hiện blocked, nhưng nếu mọi API thay đổi phải sửa mười consumer và triển khai cùng lúc, các nhóm vẫn bị coupling cao. Cần cân nhắc **module boundaries, versioning, contract tests, quyền sở hữu dữ liệu và tích hợp thường xuyên**.

Ngược lại, chỉ tạo interface và microservice mà không ai thống nhất **nghĩa của Pending**, nhóm vẫn xây sai yêu cầu. **Phối hợp sản phẩm và thiết kế kỹ thuật phải bổ trợ nhau.**

### 11.5. Dependency không nhất thiết là lý do giao việc thành chuỗi dài

Ví dụ, để có khả năng tra cứu trạng thái:

1. A và B cùng viết những trường hợp người dùng cần xem: Pending, Confirmed, Rejected, Unknown.
2. B đưa ra hợp đồng API và kiểm thử hợp đồng, A bắt đầu thử giao diện với stub phản ánh đúng hợp đồng.
3. C thử mapping API đối tác, phát hiện chỗ không thể biết kết quả.
4. Nhóm sửa hợp đồng **sớm** dựa trên bằng chứng.
5. Tích hợp luồng với backend thật và test lỗi trước khi coi là Done.

Các bước **gối nhau có kiểm soát** thay vì “A làm hết UI → bàn giao B → cuối cùng C tích hợp” giúp giảm thời gian phát hiện sai khác.

## 12. Scrum khi nhiều Scrum Team cùng làm một sản phẩm

### 12.1. Điều Scrum Guide 2020 nói rõ

Khi Scrum Team quá lớn, Scrum Guide gợi ý tổ chức thành **nhiều Scrum Team gắn kết cùng tập trung vào một sản phẩm**. Các team đó nên chia sẻ **cùng Product Goal, Product Backlog và Product Owner**. Nếu nhiều Scrum Team cùng làm một sản phẩm, họ cần **cùng định nghĩa và tuân thủ một Definition of Done**.

Các điểm quan trọng:

- **Product Owner là một người, không phải ủy ban**, chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý hiệu quả Product Backlog. Họ có thể ủy quyền việc thực hiện nhưng vẫn chịu trách nhiệm cuối cùng.
- **Developers** chịu trách nhiệm tạo kế hoạch Sprint Backlog, thực hiện công việc, chất lượng và thích ứng kế hoạch hằng ngày.
- **Scrum Master** giúp Scrum Team và tổ chức sử dụng Scrum hiệu quả, góp phần tháo cản trở và cải tiến.
- Mỗi Scrum Team có các trách nhiệm và sự kiện Scrum; **một Product Backlog chung không đồng nghĩa mọi team phải có một Sprint Backlog chung**.

Đây là các điểm về Scrum. **Các cơ chế bổ sung** như họp phối hợp kỹ thuật, workshop hợp đồng, dependency review hoặc bảng tích hợp là lựa chọn tổ chức, **không phải sự kiện Scrum bắt buộc**.

### 12.2. Một Product Owner không có nghĩa một nút cổ chai quyết định mọi chi tiết

Product Owner quyết định **thứ tự và tính minh bạch của Product Backlog**. Nhưng điều đó không buộc PO:

- Tự viết từng điều kiện SQL hoặc từng test.
- Chỉ định cá nhân làm task nào.
- Phê duyệt từng pull request kỹ thuật.
- Đơn phương quyết định giải pháp kiến trúc.
- Trả lời mọi câu hỏi nhỏ mà không có chuyên gia miền hỗ trợ.

Để tránh nút thắt, nhóm có thể phối hợp làm rõ ví dụ, tiêu chí chấp nhận, thực nghiệm và chi tiết kỹ thuật với **người có kiến thức phù hợp**. Quyền quyết định về **giá trị/ưu tiên** cần rõ, còn **cách thực hiện** thuộc trách nhiệm chuyên môn và cộng tác của Developers.

### 12.3. Một Sprint Goal của từng nhóm góp phần vào Product Goal chung

Ví dụ **một Sprint giả định**:

| Scrum Team | Sprint Goal minh họa | Liên hệ Product Goal |
| --- | --- | --- |
| **Team A** | Khách có thể nhận biết trạng thái yêu cầu khi mạng chậm trong một lát cắt đã tích hợp. | Giảm bất định khi đặt lịch. |
| **Team B** | Luồng đặt lịch không tạo trùng khi cùng yêu cầu được gửi lại. | Tăng độ tin cậy. |
| **Team C** | Tích hợp có thể phân biệt kết quả đã xác nhận và chưa xác định từ API đối tác. | Hỗ trợ hiển thị/đối soát đúng. |

Mỗi Sprint Goal là **mục tiêu cho Scrum Team đó**, không phải danh sách task do Product Owner áp đặt. Nếu các mục phụ thuộc nặng, các nhóm cần lập kế hoạch đủ sớm và tích hợp liên tục để tránh cả ba báo Goal riêng hoàn tất nhưng Product Goal không tiến triển.

### 12.4. Definition of Done chung và một Increment tích hợp

Khi nhiều Scrum Team cùng một sản phẩm, **Definition of Done chung** giúp tránh tình trạng A gọi Done khi UI chạy với mock, B gọi Done khi code compile, C gọi Done khi mapping API xong.

Một tiêu chuẩn tích hợp minh họa có thể gồm:

- Hành vi end-to-end đạt tiêu chí đã thống nhất trong môi trường phù hợp.
- Unit, contract và integration tests trọng yếu đạt.
- Không tạo dữ liệu trùng hoặc làm sai trạng thái nghiệp vụ khi retry/timeout.
- Thay đổi đạt kiểm tra bảo mật, quyền truy cập và chất lượng áp dụng.
- Tương thích hợp đồng, dữ liệu và khả năng vận hành được xem xét.
- Phần mềm đủ điều kiện tạo Increment dùng được; trạng thái chưa hoàn tất được báo trung thực.

**Scrum không quy định bộ checklist cụ thể trên cho mọi sản phẩm.** Nội dung DoD do chuẩn tổ chức hoặc Scrum Team xác định theo hướng dẫn; điều quan trọng là **không có tiêu chuẩn Done mâu thuẫn giữa các team cùng sản phẩm**.

### 12.5. Scrum events và điểm phối hợp

| Cơ hội | Nội dung cần chú ý khi có nhiều team |
| --- | --- |
| **Product Backlog refinement** | Làm rõ những PBI sắp chọn, các ví dụ nghiệp vụ, kích thước và phụ thuộc; hoạt động liên tục, không phải sự kiện Scrum bắt buộc. |
| **Sprint Planning** | Mỗi Scrum Team lập Sprint Goal, chọn PBI và tạo kế hoạch phù hợp; xem phụ thuộc với team khác. |
| **Daily Scrum** | Developers của từng team kiểm tra tiến độ tới Sprint Goal, điều chỉnh kế hoạch; không phải họp báo cáo trạng thái cho PO. |
| **Sprint Review** | Kiểm tra kết quả sản phẩm, phản hồi stakeholder và thích ứng Product Backlog khi cần. |
| **Sprint Retrospective** | Cải tiến chất lượng và hiệu quả; có thể nêu vấn đề phụ thuộc/inter-team integration. |
| **Trao đổi liên nhóm bổ sung** | Chỉ dùng khi thực sự giúp tháo phụ thuộc, tránh biến thành nhiều lớp phê duyệt. |

Nếu một tổ chức dùng framework mở rộng như **Nexus**, cần xem các quy tắc riêng của framework đó. Không nên tuyên bố họp “Scrum of Scrums” là một sự kiện bắt buộc của Scrum Guide cơ bản.

### 12.6. Tránh giấu phân bổ công việc bằng tên “PO của từng team”

Một người có thể hỗ trợ refinement hoặc đại diện nhu cầu của một lĩnh vực, nhưng nếu ba người **độc lập quyết định thứ tự của ba “Product Backlog” cho cùng một sản phẩm**, cần đánh giá xung đột với trách nhiệm Product Owner và Product Goal chung trong Scrum.

Nếu thực tế đó là **ba sản phẩm có mục tiêu và người dùng khác nhau**, việc có các Product Owner/Product Backlog riêng có thể hợp lý. Phải bắt đầu từ **ranh giới sản phẩm**, không chỉ từ sơ đồ tổ chức.

## 13. Kanban và quản lý dòng công việc ở cấp sản phẩm

### 13.1. Product Backlog là nguồn lựa chọn, workflow là dòng thực hiện

Ngay cả khi dùng Scrum, nhóm có thể áp dụng tư duy Kanban để nhìn công việc qua các bước. Một workflow minh họa:

~~~text
Product Backlog (có thứ tự)
        |
        v
Ready for Collaboration
        |
        v
In Progress --> Integration/Test --> Eligible for Release
        |             |                     |
        +-- Blocked --+                     v
                                    Released/Observed
~~~

**Không phải mọi hạng mục đi theo cùng con đường**: spike có đầu ra kiến thức, lỗi khẩn có luồng ứng cứu, feature cần bảo đảm phát hành. Khi dùng Kanban, cần định nghĩa **start/finish, trạng thái, chính sách WIP và điều kiện kết thúc rõ ràng** cho dòng đang đo.

### 13.2. Điểm chờ giữa team là một phần của cycle time sản phẩm

Giả sử một PBI:

- A làm UI trong 2 ngày.
- Chờ B hoàn tất hợp đồng API 5 ngày.
- B chỉnh backend 2 ngày.
- Chờ môi trường tích hợp 4 ngày.
- Kiểm tra đầu-cuối 2 ngày.

Nếu các bước nối tiếp và không chồng lấp, **thời gian từ bắt đầu tới xong là 15 ngày**, dù tổng thời gian xử lý trực tiếp chỉ là 6 ngày. Chi phí chờ (5 + 4 = **9 ngày**) là một phần quan trọng của trải nghiệm giao hàng.

Nếu dashboard của A chỉ đo “2 ngày hoàn tất task UI”, nó **không phản ánh tốc độ giao giá trị**. Đo flow ở phạm vi sản phẩm phải công khai điểm bắt đầu và kết thúc liên quan tới người dùng, hoặc có một chỉ số bổ sung cho thời gian tới phát hành.

### 13.3. Hạn chế WIP xuyên nhóm

Nếu A, B, C liên tục bắt đầu việc mới nhưng PBI tích hợp cũ vẫn chờ, Product Backlog có thể có thứ tự đúng mà **dòng giá trị vẫn nghẽn**.

Nhóm có thể thiết lập:

- Giới hạn số **lát cắt liên nhóm đang triển khai**.
- Chính sách ưu tiên giúp hoàn tất hạng mục đang gần Done.
- Điều kiện kéo PBI mới khi năng lực ở điểm nghẽn có thể tiếp nhận.
- Tín hiệu blocked và cách liên hệ người có quyền giải quyết.
- Ngoại lệ minh bạch cho sự cố khẩn hoặc nghĩa vụ bắt buộc.

**WIP limit không phải mục tiêu tự thân**. Nếu đặt quá thấp khiến công việc quan trọng bị chặn hoặc không có nguồn lực ứng cứu, cần điều chỉnh theo bằng chứng.

### 13.4. Đo flow ở cấp sản phẩm

| Số đo | Câu hỏi | Cẩn trọng |
| --- | --- | --- |
| **WIP** | Có bao nhiêu hạng mục đang nằm trong workflow đã định nghĩa? | Nên xem loại việc và những mục blocked. |
| **Throughput** | Bao nhiêu hạng mục đạt điểm kết thúc mỗi kỳ? | Item phải có quy mô và loại đủ hiểu; không biến ticket vụn thành “thành công”. |
| **Cycle time** | Thời gian từ start tới finish của các mục hoàn tất? | Phải giữ ranh giới nhất quán, không che thời gian chờ release. |
| **Work item age** | Hạng mục đang mở đã nằm trong workflow bao lâu? | Giúp phát hiện việc khó bị bỏ quên. |
| **SLE** | Mức kỳ vọng thời gian phục vụ theo lịch sử/thỏa thuận. | Là kỳ vọng có mức tin cậy, không phải cam kết 100% mọi trường hợp. |
| **Blocker duration** | Việc bị chặn vì API, review, môi trường bao lâu? | Nên dùng để tháo giới hạn hệ thống, không đổ lỗi cá nhân. |

Nếu toàn sản phẩm dùng nhiều board, có thể tổng hợp theo **lát cắt kết quả**, tránh **đếm task nội bộ của ba team như ba feature độc lập được giao**.

### 13.5. Không dùng số đo để ép mọi người tối đa hóa độ bận

Khi B là nút thắt, việc A và C có ít ticket đang xử lý có thể là cơ hội giúp thử nghiệm, giảm rủi ro và hoàn tất tích hợp. **Utilization cá nhân cao** thường không phải mục tiêu tốt cho hệ thống tri thức biến động; nhiều việc bắt đầu đồng thời có thể tăng thời gian chờ.

## 14. Điều phối kỹ thuật: một thứ tự sản phẩm cần khả năng tích hợp thật

### 14.1. “Đã hoàn tất phần của nhóm” không tự tạo Increment

Trong một sản phẩm có nhiều nhóm, trạng thái của một PBI **phải phản ánh khả năng dùng được của hành vi**, không chỉ tổng số task đã hoàn thành:

~~~mermaid
flowchart TD
    PBI["PBI: Khách tra cứu trạng thái đặt lịch"] --> API["B: API trạng thái có thẩm quyền"]
    PBI --> UI["A: Giao diện tra cứu"]
    PBI --> PARTNER["C: Mapping trạng thái API đối tác"]
    API --> TEST["Contract + integration tests"]
    UI --> TEST
    PARTNER --> TEST
    TEST --> DONE{"Đã đạt chuẩn tích hợp và chất lượng?"}
    DONE -->|Chưa| FIX["Làm rõ lỗi/phụ thuộc và tiếp tục"]
    FIX --> TEST
    DONE -->|Rồi| INC["Increment có thể sử dụng"]
~~~

Sơ đồ minh họa một PBI có thể được thực hiện bởi nhiều người và nhiều mô đun. Trong Scrum, **chỉ tính vào Increment khi đáp ứng Definition of Done**. “Code đã merge” chưa đủ nếu tiêu chí chất lượng và hành vi tích hợp chưa đạt.

### 14.2. Hợp đồng ổn định về ý nghĩa, không chỉ chữ ký

Ví dụ một API:

~~~json
{
  "requestId": "req-example-01",
  "bookingStatus": "PENDING",
  "confirmedAppointmentId": null
}
~~~

Payload chỉ minh họa. Cần thống nhất:

- PENDING nghĩa là **đã tiếp nhận** nhưng chưa có kết quả cuối hay là đang xử lý ở UI?
- Trạng thái có thể chuyển thành gì, trong thời hạn nào?
- Trường **confirmedAppointmentId** có lúc nào xuất hiện khi status chưa CONFIRMED không?
- Khi timeout, client có được gửi lại cùng một idempotency key không?
- Ai có quyền tra cứu và người dùng nào được xem thông tin?
- Phiên bản contract thay đổi thế nào để consumer cũ không diễn giải sai?

**Một hợp đồng compile đúng nhưng hiểu sai trạng thái vẫn có thể làm người dùng gặp lỗi nghiêm trọng.** Vì vậy cần ví dụ chấp nhận chung và contract tests ở ranh giới.

### 14.3. Các công cụ kỹ thuật bổ trợ

| Thực hành | Lợi ích khi nhiều nhóm cùng làm | Giới hạn |
| --- | --- | --- |
| **Continuous Integration (CI)** | Phát hiện thay đổi giữa mô đun/nhóm làm hỏng build hoặc test sớm. | CI chỉ tốt khi test có ý nghĩa và môi trường đáng tin. |
| **Contract tests** | Kiểm tra consumer/provider hiểu cùng hợp đồng ở ranh giới. | Không thay thế kiểm thử end-to-end và bất biến dữ liệu. |
| **Feature flags** | Cho phép tách một số hoạt động tích hợp và mở tính năng có kiểm soát. | Tắt flag không tự hoàn tác giao dịch/sự kiện đã xảy ra. |
| **Refactoring** | Giảm coupling khiến một PBI nhỏ phải sửa nhiều phần. | Phải bảo vệ hành vi bằng test và xem phạm vi rủi ro. |
| **TDD** | Giúp nhóm thống nhất hành vi, kiểm tra trường hợp biên và sửa cấu trúc an toàn. | Test không thay đối thoại với chuyên gia nghiệp vụ. |
| **Pairing/mob collaboration** | Chia sẻ kiến thức và giải quyết phụ thuộc khó qua nhóm. | Cần chọn vấn đề phù hợp, không ép mọi task thành cuộc họp đông người. |
| **Integrated testing** | Chứng minh nhiều thành phần cùng tạo được kết quả sản phẩm. | Không nên đợi cuối kỳ mới chạy tất cả test. |
| **Progressive delivery** | Học từ sử dụng thật khi đủ điều kiện an toàn. | Cần guardrails, hỗ trợ và quản lý trạng thái/dữ liệu. |

Những thực hành gắn với XP và kỹ thuật hiện đại có thể hỗ trợ một Scrum Team hoặc nhóm dùng Kanban. **Không cần tuyên bố mọi tổ chức phải chọn XP toàn bộ** mới có thể dùng TDD, CI hay refactoring.

### 14.4. Một Definition of Done chung không đủ nếu không thực thi

Viết “đã kiểm thử tích hợp” trong checklist sẽ vô ích nếu môi trường chưa có, API đối tác luôn mock và không ai có trách nhiệm xem lỗi. Nhóm cần:

- Một đường CI kiểm tra tích hợp có ý nghĩa.
- Những test bất biến quan trọng, ví dụ concurrent booking.
- Cách tạo dữ liệu giả đúng, tách khỏi dữ liệu cá nhân thật.
- Mô tả “đủ điều kiện release” và “đã phát hành” khác nhau ở đâu.
- Khi build hỏng, có chính sách cùng sửa thay vì chỉ đổ lỗi sang nhóm cuối.

**Một Product Backlog có thứ tự chỉ có giá trị khi sản phẩm có khả năng giao từng lát cắt đáng tin.**

### 14.5. Chia sẻ tri thức để không tạo nút thắt vô hình

Nếu chỉ một chuyên gia B hiểu transaction chống trùng, mọi feature đều chờ người ấy. Có thể cân nhắc:

- Pairing có chủ đích trên một thay đổi trọng yếu.
- Tài liệu ngắn về bất biến, kiến trúc và API.
- Reviewer dự phòng có năng lực phù hợp.
- Contract tests giúp người ngoài mô đun hiểu hành vi công khai.
- Cắt phạm vi PBI để giảm số thay đổi đồng thời cần người đó.

**Không loại bỏ review chất lượng chỉ để bớt chờ.** Mục tiêu là tăng khả năng chia sẻ tri thức và năng lực, không khiến người ít hiểu domain tùy tiện thay đổi bất biến.

## 15. Ví dụ xuyên suốt: một Product Backlog cho ba nhóm

Tất cả ví dụ, năng lực và số liệu ở phần này đều **giả định phục vụ học tập**.

### 15.1. Product Goal và nguồn phản hồi

Nền tảng đặt lịch có Product Goal:

> “Khách có thể đặt và tra cứu lịch tư vấn đáng tin trên điện thoại, không phải gọi tổng đài vì thiếu thông tin trạng thái.”

Trong kỳ vừa qua, nhóm nhận:

1. Phản ánh khách **nhấn Đặt lịch nhiều lần** khi mạng chậm.
2. QA tìm thấy một đường lỗi có thể tạo hai lịch khi xử lý retry.
3. Nhóm hỗ trợ có nhiều cuộc gọi hỏi **đã xác nhận hay chưa**.
4. Sales muốn bổ sung SMS sau đặt lịch.
5. Khách muốn tự **đổi lịch** trước giờ tư vấn.
6. Đối tác API chưa xác nhận hành vi khi request timeout.

Thay vì tạo sáu danh sách con giao cho từng nhóm, Product Owner cùng Developers và chuyên gia miền nhận diện **điều cần sửa để đạt Product Goal**, những quyết định bị chặn và khả năng tạo một Increment an toàn.

### 15.2. Một danh sách có thứ tự ban đầu

| Thứ tự ban đầu | ID | Hạng mục | Giá trị/rủi ro chính | Nhóm liên quan |
| ---: | --- | --- | --- | --- |
| **1** | **P01** | Sửa đường retry có thể tạo lịch trùng, kèm test hồi quy. | Bảo vệ dữ liệu và độ tin cậy. | B, C |
| **2** | **P02** | Xác minh hợp đồng timeout/idempotency của API đối tác. | Giảm bất định đang chặn thiết kế. | C, B |
| **3** | **P03** | Cung cấp trạng thái yêu cầu có thẩm quyền để tra cứu. | Mở khóa trải nghiệm và đối soát. | B, C |
| **4** | **P04** | Hiển thị và tra cứu Pending/Confirmed/Rejected an toàn. | Khách biết kết quả, ít gửi lặp. | A, B |
| **5** | **P05** | Theo dõi số yêu cầu gửi lặp và thời gian xác nhận. | Bằng chứng outcome và vận hành. | A, B, C |
| **6** | **P06** | Đổi lịch cơ bản, không phí, trong thời hạn hợp lệ. | Mở rộng tự phục vụ. | A, B, C |
| **7** | **P07** | Gửi SMS xác nhận khi đã có trạng thái phù hợp. | Tiện ích bổ sung, cần chứng minh nhu cầu. | C, A |

**Thứ tự này là minh họa, không phải quy tắc tuyệt đối.** P01 được đánh giá nghiêm trọng và cần xử lý an toàn; nếu đó là sự cố production đang xảy ra, việc ứng cứu có thể bắt đầu **ngay trước khi diễn ra phiên sắp thứ tự Product Backlog**. P05 có thể triển khai một phần sớm để có bằng chứng, miễn không làm sai mục tiêu và tốn tải không cần thiết.

### 15.3. Vì sao P02 đứng trước một feature hiển thị?

Nếu API đối tác trả timeout sau khi đã xử lý, UI không thể cứ hiển thị **Rejected**. Cần hiểu liệu backend có thể truy vấn lại trạng thái, gửi cùng idempotency key và đối soát.

Một spike **P02** có thể:

- Kiểm tra tài liệu/hợp đồng API.
- Thử request gửi lặp trong sandbox.
- Mô phỏng timeout, truy vấn trạng thái và kiểm tra tính nhất quán.
- Kết luận **có đủ bằng chứng** hay còn trường hợp **Unknown** phải xử lý.
- Cập nhật các PBI, hợp đồng và test.

**P02 không được gọi là feature hoàn tất cho khách**; nó cung cấp bằng chứng để chọn phương án an toàn và tránh xây sai hàng loạt chức năng.

### 15.4. Làm rõ quyền quyết định

| Quyết định | Người chịu trách nhiệm/đóng góp | Giới hạn |
| --- | --- | --- |
| P01/P02/P04 đứng ở thứ tự nào trong Product Backlog? | **Product Owner** chịu trách nhiệm về thứ tự, dựa trên đóng góp của Developers và stakeholder. | Vấn đề ứng cứu khẩn cần quy trình an toàn tương ứng. |
| API trạng thái biểu diễn Pending/Unknown thế nào? | Developers và chuyên gia nghiệp vụ phối hợp; Product Owner làm rõ giá trị/yêu cầu. | Không tự coi kỹ thuật có quyền đổi chính sách nghiệp vụ. |
| Team nào chọn những PBI nào trong Sprint? | **Developers** lập kế hoạch với Scrum Team trong Sprint Planning. | Không giao task cá nhân từ bảng xếp hạng sản phẩm. |
| Lỗi tạo trùng đã đủ điều kiện Done chưa? | Developers kiểm chứng theo **Definition of Done**, tiêu chí an toàn và chuyên môn liên quan. | Không đánh dấu Done vì code compile. |
| Khi nào mở pilot? | Vai trò có quyền release và vận hành theo chính sách sản phẩm/tổ chức, với bằng chứng thích hợp. | Sprint Review không tự là cổng phê duyệt bắt buộc. |

### 15.5. Lịch phối hợp mẫu, không phải cam kết ngày

~~~text
Giai đoạn học/điều chỉnh ngắn:

Team C: [P02 - thử timeout/idempotency] ----> [hợp đồng/adapter rõ]
Team B: [P01 - sửa và test chống trùng] ----> [P03 - trạng thái]
Team A: [thử UI Pending với dữ liệu giả] ---> [P04 - tích hợp API thật]
                                               |
                                               v
                     [Contract + integration tests + kiểm tra sử dụng]
                                               |
                                               v
                           [Increment đạt chuẩn, quan sát kết quả]
~~~

Các phần việc có thể **gối nhau** khi dùng hợp đồng và test, nhưng phải liên tục tích hợp và công khai nếu P02 phát hiện kết quả API khác dự đoán. Một stub UI không tự chứng minh P04 Done.

### 15.6. Một kế hoạch năng lực minh họa

Giả sử trong một cửa sổ hai tuần, **khả năng công việc khả dụng sau khi trừ nghỉ phép và trách nhiệm thường xuyên** được ước lượng theo *person-days* của từng nhóm:

| Nhóm | Năng lực khả dụng giả định | Công việc chủ đạo dự kiến | Dự phòng/phối hợp |
| --- | ---: | --- | --- |
| **A** | 14 ngày công | 5 ngày thử/trình bày UI trạng thái; 4 ngày tích hợp; 3 ngày accessibility/test. | 2 ngày dự phòng/phối hợp. |
| **B** | 16 ngày công | 6 ngày sửa lỗi chống trùng; 4 ngày API trạng thái; 4 ngày test/đối soát. | 2 ngày dự phòng/ứng cứu. |
| **C** | 12 ngày công | 3 ngày thử API; 4 ngày adapter; 3 ngày contract/integration test. | 2 ngày dự phòng phụ thuộc. |

Các phép cộng: A \(5+4+3+2=14\), B \(6+4+4+2=16\), C \(3+4+3+2=12\). Đây là **ngân sách minh họa**, không phải cách Scrum bắt buộc ước lượng, không phải lời hứa mọi PBI sẽ hoàn tất trong hai tuần, và không được cộng ngày công rồi suy ra đường găng tự động.

Nếu P02 trả kết quả xấu, C có thể phải dành thêm thời gian đối soát, B đổi thiết kế và A điều chỉnh cách hiển thị. Product Owner và Developers phải **thương lượng lại phạm vi/dự báo dựa trên bằng chứng**, không yêu cầu cả ba nhóm “bù tốc độ” bằng cách giảm chuẩn chất lượng.

### 15.7. Cách nhận biết kết quả thay vì chỉ nhìn ticket

Một Increment có ích trong ví dụ có thể chứng minh:

- Khách gửi cùng yêu cầu nhiều lần không tạo hai lịch trùng theo quy tắc.
- Khách tra cứu được trạng thái có thẩm quyền, không cần gửi thêm request.
- Pending/Confirmed/Rejected/Unknown được diễn đạt đúng bối cảnh.
- API và các adapter đạt kiểm thử hợp đồng và tích hợp.
- Có giám sát lỗi/gửi lặp để học từ môi trường thật khi phát hành an toàn.

Nếu A đánh dấu UI Done, B đánh dấu API Done nhưng C vẫn chưa giải quyết timeout ảnh hưởng bất biến, **toàn PBI chưa đạt chuẩn tích hợp**. Trạng thái sản phẩm phải thể hiện thực tế đó.

### 15.8. Ví dụ quan sát outcome sau một vòng giao

Giả sử hai kỳ quan sát **không phải thử nghiệm có nhóm đối chứng**, với định nghĩa số đo nhất quán:

| Tín hiệu giả định | Trước | Sau |
| --- | ---: | ---: |
| Phiên bắt đầu đặt lịch | 400 | 500 |
| Phiên có lịch Confirmed trong 24 giờ | 280 | 375 |
| Tỷ lệ completion theo phiên | **70%** | **75%** |
| Phiên có ít nhất một submit | 320 | 400 |
| Phiên có submit lặp | 80 | 64 |
| Tỷ lệ submit lặp trong phiên đã submit | **25%** | **16%** |
| Liên hệ hỗ trợ về xác nhận | 40 | 30 |
| Lỗi đặt trùng đã xác minh | 0 | 0 |

Kiểm tra: \(280/400=70\%\); \(375/500=75\%\); \(80/320=25\%\); \(64/400=16\%\). Tỷ lệ liên hệ hỗ trợ trên 100 phiên bắt đầu giảm từ **10** xuống **6**, nếu các định nghĩa phân loại không đổi.

**Diễn giải:** Có tín hiệu tích cực về completion và submit lặp, nhưng các nhóm thay nhiều thứ cùng lúc, số người dùng khác và mẫu có thể thay đổi. Không thể tuyên bố riêng P04 **gây ra toàn bộ cải thiện**. Lỗi đặt trùng bằng 0 trong hai kỳ **không chứng minh rủi ro hiếm đã biến mất**; vẫn cần test và giám sát.

### 15.9. Product Backlog thay đổi sau khi học

Sau phát hành giới hạn và hỗ trợ:

- Nếu phần lớn khách vẫn hiểu sai Pending, **nội dung và UX tiếp tục được ưu tiên**.
- Nếu API timeout thường xuyên hơn dự báo, **đối soát/observability có thể lên trước tính năng đổi lịch**.
- Nếu SMS ít được yêu cầu và chi phí đáng kể, **P07 có thể hạ thứ tự hoặc bị loại**.
- Nếu self-service đổi lịch cho nhóm khách phổ biến đã được xác minh có giá trị, P06 được chia thành lát cắt an toàn.
- Nếu một sự cố nghiêm trọng phát sinh, **triage và kế hoạch của các nhóm phải thích ứng**.

Điều thay đổi là **đường tới Product Goal**, không phải nguyên tắc “mỗi team phải giữ nguyên bảng kế hoạch đã chốt bất chấp bằng chứng mới”.

## 16. Điều chỉnh thứ tự khi thông tin hoặc năng lực thay đổi

Một Product Backlog chung không phải danh sách được khóa vào đầu quý. Thứ tự cần thay đổi **khi bằng chứng về giá trị, rủi ro, phụ thuộc hoặc năng lực thay đổi**, nhưng việc thích ứng phải minh bạch để các nhóm không liên tục bị ngắt việc không lý do.

### 16.1. Bốn loại biến cố thường gặp

| Biến cố | Ví dụ | Tác động có thể xảy ra | Quyết định cần làm rõ |
| --- | --- | --- | --- |
| **Phản hồi người dùng** | Khách vẫn nhấn gửi lại dù đã thêm spinner. | Giả thuyết UI ban đầu chưa đúng. | Cần test cách diễn giải trạng thái hay sửa API? |
| **Rủi ro/chất lượng** | Xuất hiện lỗi giao dịch tạo trùng đã xác minh. | Công việc khác có thể phải nhường năng lực ứng cứu. | Ai chịu trách nhiệm xử lý, PBI nào được trì hoãn? |
| **Phụ thuộc** | Đối tác chưa hỗ trợ truy vấn kết quả sau timeout. | Lát cắt đổi lịch không thể giả định Confirmed ngay. | Làm discovery, đổi thiết kế hay giảm phạm vi? |
| **Năng lực** | Nhóm C phải hỗ trợ một sự cố lớn trong một tuần. | PBI cần tích hợp không thể dự báo như cũ. | Có thể đổi thứ tự việc độc lập hay phải cập nhật forecast? |

Một thay đổi **ở phạm vi sản phẩm** có thể ảnh hưởng kế hoạch từng Scrum Team. Trong Scrum, Sprint Goal vẫn là cam kết giúp tập trung; khi cần thích ứng, Developers và Product Owner thảo luận việc thay đổi phạm vi mà không làm giảm chất lượng hoặc đơn phương coi Sprint Goal là vô nghĩa.

### 16.2. Quy trình điều chỉnh theo bằng chứng

~~~mermaid
flowchart TD
    A["Bằng chứng mới hoặc trở ngại"] --> B["Xác định điều gì đã đổi"]
    B --> C["Đánh giá tác động tới Product Goal, rủi ro và phụ thuộc"]
    C --> D["Xem PBI đang làm, WIP, năng lực và điều kiện an toàn"]
    D --> E["Cân nhắc lựa chọn: đổi thứ tự, giảm lát cắt, thử thêm, giữ nguyên"]
    E --> F["Product Owner cập nhật Product Backlog khi cần"]
    F --> G["Các nhóm điều chỉnh kế hoạch thực thi phù hợp"]
    G --> H["Thông báo đánh đổi và cập nhật forecast"]
    H --> I["Kiểm chứng bằng Increment và outcome"]
~~~

Không nhất thiết họp tất cả nhóm cho một thay đổi nhỏ. Nếu một lỗi bảo mật nghiêm trọng đang xảy ra, đường ứng cứu **được kích hoạt ngay theo chính sách**, rồi mới cập nhật đầy đủ kế hoạch. Nếu chỉ đổi nội dung một PBI chưa sắp chọn, Product Owner có thể xử lý nhẹ nhàng hơn.

### 16.3. Tránh “priority ping-pong”

Nếu mỗi stakeholder có thể trực tiếp chuyển ticket của team mình lên đầu mà không giải thích đánh đổi, các nhóm bị **đổi hướng liên tục**. Kết quả thường là WIP cao, nhiều việc dở dang và ít Increment dùng được.

Một chính sách đơn giản có thể gồm:

- Mọi nhu cầu mới được ghi rõ **vấn đề, giá trị, rủi ro và căn cứ**.
- Có đường riêng để **triage sự cố khẩn**.
- Product Owner chịu trách nhiệm quyết định thứ tự PBI của sản phẩm và công khai lý do.
- Developers giúp nêu **kích thước, rủi ro, phụ thuộc và khả năng hoàn tất**.
- Việc đổi PBI đang làm phải xem **chi phí gián đoạn, Sprint Goal và Definition of Done**.
- Các thay đổi quan trọng được thông báo với **PBI nào tiến lên và PBI nào lùi lại**.

**Thứ tự có thể thay đổi thường xuyên khi cần; quyền tùy tiện đổi không lý do không phải tính thích ứng Agile.**

### 16.4. Mẫu thông báo thay đổi thứ tự

> “Kết quả thử API đối tác cho thấy timeout có thể xảy ra sau khi yêu cầu đổi lịch đã được tiếp nhận. Vì rủi ro tạo yêu cầu trùng, Product Backlog sẽ đưa kiểm chứng/đối soát trạng thái lên trước chức năng SMS. Nhóm C làm rõ giới hạn API; nhóm B bảo vệ trạng thái và transaction; nhóm A vẫn thử luồng hiển thị với dữ liệu giả đúng hợp đồng. Chúng ta chưa cam kết ngày phát hành đổi lịch cho tới khi kiểm chứng đường xử lý Unknown. Ảnh hưởng tới phạm vi và forecast sẽ được cập nhật tại điểm xem lại tiếp theo.”

Thông báo tập trung vào **bằng chứng, lý do, đánh đổi và quyết định**, không chỉ “ưu tiên mới là 1”.

### 16.5. Không biến một deadline giả thành điều kiện bất biến

Nếu một stakeholder nói “phải có SMS trước thứ Sáu” nhưng không có hậu quả cụ thể của việc trễ, cần làm rõ **tính cấp bách thực**. Nếu là nghĩa vụ hợp đồng có hiệu lực, đó là ràng buộc khác với một mong muốn nội bộ. Trong cả hai trường hợp, nên minh bạch **phạm vi tối thiểu, rủi ro chất lượng và lựa chọn đánh đổi**, không chỉ tăng giờ làm để bù cho kế hoạch thiếu căn cứ.

## 17. Nhịp phối hợp và quyền ra quyết định

### 17.1. Một cơ chế gọn giúp nhiều nhóm không chờ nhau

Không có một số lượng cuộc họp bắt buộc cho mọi tổ chức. Một nhịp phối hợp có thể gồm:

| Hoạt động | Mục đích | Ai cần có mặt? | Đầu ra |
| --- | --- | --- | --- |
| **Intake/triage khi có tín hiệu** | Phân loại sự cố, vấn đề, ý tưởng hoặc discovery. | Người tiếp nhận, người có trách nhiệm sản phẩm/kỹ thuật theo loại việc. | Điều kiện xử lý ngay hoặc bổ sung vào nguồn backlog. |
| **Refinement theo nhu cầu** | Làm rõ PBI gần, phụ thuộc, test và lát cắt. | Product Owner, Developers/người hiểu miền liên quan. | Hạng mục đủ rõ cho quyết định sắp tới, rủi ro hiện ra. |
| **Phối hợp dependency ngắn** | Tháo những điểm chặn giữa team. | Người **thực sự** tham gia phụ thuộc. | Owner, bước tiếp và thời điểm kiểm tra. |
| **Lập kế hoạch Sprint/flow** | Chọn công việc phù hợp mục tiêu và năng lực thực. | Theo trách nhiệm của Scrum Team hoặc workflow đang dùng. | Kế hoạch khả thi, minh bạch việc đang làm. |
| **Kiểm tra Increment và phản hồi** | Học về outcome, chất lượng, kế hoạch tiếp theo. | Scrum Team và stakeholder phù hợp. | Bằng chứng, điều chỉnh backlog khi cần. |
| **Retrospective/cải tiến dòng** | Nhìn phụ thuộc, WIP, test và cách làm việc. | Các bên chịu ảnh hưởng theo phạm vi cải tiến. | Một số thử nghiệm có chủ đích, theo dõi kết quả. |

**Không cần tạo một họp “đồng bộ mọi thứ” mỗi ngày** nếu phần lớn người tham gia không có phụ thuộc chung. Họp ngắn đúng người, hợp đồng rõ và board minh bạch thường tốt hơn nhiều lớp báo cáo.

### 17.2. Quyền quyết định khác quyền tham gia

| Quyết định | Ai chịu trách nhiệm chính? | Ai cần tham gia làm rõ? |
| --- | --- | --- |
| Giá trị và thứ tự PBI trong Scrum | **Product Owner**. | Developers, stakeholder, người dùng/chuyên gia miền. |
| Sprint Backlog và cách thực thi | **Developers** thuộc Scrum Team. | Product Owner để làm rõ giá trị và phạm vi. |
| Cơ chế bảo vệ dữ liệu và thiết kế kỹ thuật | Developers/người có thẩm quyền kỹ thuật; tuân chuẩn chất lượng/tổ chức. | Người hiểu nghiệp vụ, vận hành, bảo mật khi phù hợp. |
| Ứng cứu production | Theo **quy trình incident** và người có quyền ứng cứu. | Product Owner và những bên cần phối hợp để biết ảnh hưởng sản phẩm. |
| Ưu tiên đầu tư giữa **các sản phẩm khác nhau** | Cấp chịu trách nhiệm chiến lược/portfolio theo tổ chức. | Chủ sản phẩm và nhóm liên quan. |
| Ngừng/mở rộng phát hành | Người có thẩm quyền release/vận hành theo chính sách. | Product Owner, Developers, support và stakeholder cần thiết. |

Không dùng bảng này để tạo các chức danh bắt buộc ngoài Scrum. Nó nhấn mạnh cần **định nghĩa điểm quyết định**; một quyết định giá trị, một thay đổi kiến trúc và ứng cứu sự cố có thẩm quyền khác nhau.

### 17.3. Lựa chọn cơ chế “Scrum of Scrums” có chủ đích

Nhiều tổ chức dùng một cuộc trao đổi liên nhóm kiểu **Scrum of Scrums** để xử lý phụ thuộc và tích hợp. Đây có thể là thực hành hữu ích, nhưng **không phải sự kiện bắt buộc của Scrum Guide cơ bản**.

Nó hiệu quả hơn khi:

- Có danh sách **phụ thuộc cụ thể và người có khả năng hành động**.
- Trao đổi tập trung vào **trở ngại cần giải quyết**, không lặp báo cáo từng người.
- Không để những quyết định giá trị sản phẩm bị thay bởi thứ tự ai lên tiếng trước.
- Có đường đưa thông tin lại nhóm và cập nhật Product Backlog/forecast khi thích hợp.

Nếu cuộc họp chủ yếu đọc status trong tool mà không tháo phụ thuộc, hãy thử **làm rõ board và chỉ trao đổi những điểm đang bị chặn**.

### 17.4. Đừng cố giải mọi vấn đề bằng “thêm coordinator”

Khi một feature cần ba nhóm sửa cùng một schema, thêm một người tổng hợp danh sách “ai chờ ai” có thể giúp nhìn vấn đề nhưng **không thay được ranh giới kiến trúc và hợp đồng dữ liệu**. Cần phân tích vì sao việc thay schema lại lan rộng: ownership, coupling, versioning hay nghiệp vụ phải nhất quán.

**Phối hợp tổ chức và cải tiến kỹ thuật phải đi cùng nhau**. Một nút thắt có thể giảm bằng pairing và đào tạo, hoặc bằng ranh giới API tốt hơn, chứ không nhất thiết bằng thêm cấp duyệt.

## 18. Đo hiệu quả ưu tiên ở phạm vi sản phẩm

Một Product Backlog có thứ tự đẹp không có giá trị nếu sản phẩm vẫn không giải quyết nhu cầu, chất lượng giảm hoặc thời gian chờ quá lớn. **Đo outcome, flow và chất lượng cùng nhau**.

### 18.1. Ba lớp tín hiệu

| Lớp | Tín hiệu ví dụ | Câu hỏi |
| --- | --- | --- |
| **Outcome của sản phẩm** | Tỷ lệ đặt lịch thành công, tỷ lệ khách tự tra cứu được trạng thái, số liên hệ hỗ trợ. | Sản phẩm có giải quyết đúng vấn đề quan trọng không? |
| **Flow end-to-end** | Cycle time của PBI tới điểm Done/integrated; thời gian chờ; throughput; work item age. | Nhiều nhóm có đưa lát cắt có giá trị qua hệ thống nhanh hơn không? |
| **Chất lượng và bền vững** | Sự cố, lỗi hồi quy, dữ liệu sai, khả năng phục hồi, tải ứng cứu. | Cải thiện tốc độ có làm khách chịu thiệt hại hoặc đội kiệt sức không? |

Các số đo cần có **định nghĩa, nguồn dữ liệu, kỳ quan sát và giới hạn**. Không dùng chúng để xếp hạng cá nhân hoặc so trực tiếp các nhóm có công việc khác nhau.

### 18.2. Một ví dụ tính tỷ lệ blocked

Giả sử trong một tuần, ở thời điểm kiểm tra thống nhất:

- Có **20 PBI** đang trong workflow của sản phẩm.
- **7 PBI** đang blocked vì phụ thuộc.
- Trong 7 PBI đó, **4 PBI** chờ hợp đồng API và **3 PBI** chờ môi trường tích hợp.

Tỷ lệ bị chặn tại thời điểm ấy:

\[
\frac{7}{20}\times100\% = 35\%
\]

Điều này **không có nghĩa 35% tổng thời gian làm việc đã mất**: đây là một **snapshot theo số hạng mục**, không phải đo thời lượng. Để hiểu chi phí thật, cần thêm **blocked duration, work item age và vị trí trên đường giao giá trị**.

### 18.3. Một ví dụ phân biệt throughput và outcome

Trong một tuần, ba nhóm đóng **30 task** kỹ thuật; nhưng sản phẩm chỉ có **3 PBI đạt Definition of Done**, trong đó một PBI là sửa lỗi bảo mật, hai PBI tạo năng lực mới. Không nên nói “đã giao 30 tính năng”.

Nếu tuần sau nhóm đóng 20 task nhưng có 5 PBI tích hợp có ích và độ tin cậy không giảm, kết quả có thể tốt hơn, tùy kích thước, giá trị và chất lượng từng PBI. **Đếm task không đo được giá trị** nếu các task chỉ là những bước nội bộ.

### 18.4. Đo thời gian từ quyết định tới giá trị

Một hạng mục có thể:

1. Chờ Product Owner làm rõ.
2. Được chọn để phát triển.
3. Đi qua nhiều nhóm.
4. Tích hợp đạt Done.
5. Chờ release.
6. Được người dùng sử dụng và có bằng chứng outcome.

Mỗi điểm có câu hỏi khác nhau. Nếu chỉ đo **thời gian code** sẽ bỏ qua waiting ở refinement/QA/release. Nếu đo **lead time từ yêu cầu tới phát hành**, phải thống nhất lúc “yêu cầu bắt đầu” và cách xử lý hạng mục discovery hoặc nhu cầu bị loại.

Không nhất thiết có đúng một “lead time” cho mọi cấp. Hãy **nêu ranh giới và đơn vị** mỗi chỉ số để không diễn giải sai.

### 18.5. Little’s Law và dự báo dòng một cách thận trọng

Với hệ thống ổn định trong một ranh giới thống nhất, quan hệ Little’s Law là:

\[
\text{WIP trung bình}=\text{Throughput trung bình}\times\text{Thời gian trung bình trong hệ thống}
\]

Nếu WIP trung bình ở phạm vi sản phẩm là **12 PBI** và throughput trung bình là **4 PBI/tuần**, thời gian trung bình theo mô hình xấp xỉ **3 tuần/PBI**. Đây **không phải cam kết** mỗi PBI xong trong ba tuần; phân bố có thể rất rộng và hệ thống có thể không ổn định.

Nếu nhóm “giảm WIP” bằng cách đẩy việc chờ tích hợp ra ngoài điểm finish đã khai báo, công thức vẫn có thể cho số đẹp nhưng **người dùng không nhận giá trị nhanh hơn**. Cần xem ranh giới và điều kiện Done.

### 18.6. Kết hợp định tính và định lượng khi đổi thứ tự

Một tỷ lệ completion giảm có thể do giờ tư vấn khan hiếm, mạng chậm hoặc giao diện rối. Số liệu **không tự chỉ ra nguyên nhân**. Phỏng vấn, thử sử dụng và log kỹ thuật có thể hỗ trợ. Khi điều chỉnh thứ tự Product Backlog, nên công khai:

- **Điều quan sát:** Số đo nào đổi, ở phân đoạn nào?
- **Điều suy luận:** Nguyên nhân giả định nào?
- **Mức tin cậy:** Dữ liệu đầy đủ không, có biến số nhiễu không?
- **Quyết định:** Sửa ngay, thử nhỏ, theo dõi thêm hay dừng ý tưởng?

Một Product Backlog tốt không phải bảng xếp hạng bất biến; nó là **bản đồ các lựa chọn tốt nhất từ hiểu biết hiện có**.

## 19. Những phản mẫu khi quản lý backlog qua nhiều nhóm

| Phản mẫu | Biểu hiện | Hậu quả | Điều chỉnh thực dụng |
| --- | --- | --- | --- |
| **Một sản phẩm, ba Product Backlog cạnh tranh** | Mỗi nhóm chọn ưu tiên không có điểm quy chiếu chung. | Các phần riêng xong nhưng hành trình người dùng chưa dùng được. | Xác định Product Goal, một nguồn thứ tự sản phẩm và các board thực thi liên kết. |
| **Đổi tên board thành “Product Backlog”** | Công cụ mới nhưng trách nhiệm và xung đột không đổi. | Minh bạch hình thức, ưu tiên vẫn bị phân mảnh. | Làm rõ ranh giới sản phẩm, quyền quyết định và cách triage. |
| **Tất cả hạng mục đều High Priority** | Không ai nêu cái gì phải chờ. | Năng lực bị chia mỏng, khó quyết định khi có rủi ro. | Sắp thứ tự và công khai đánh đổi khi thay thứ tự. |
| **PO giao việc cá nhân từ trên xuống** | Product Backlog biến thành bảng phân công developer. | Giảm khả năng tự tổ chức và đưa ra thiết kế kỹ thuật. | PO quyết định giá trị/trật tự; Developers lập kế hoạch thực thi trong trách nhiệm của họ. |
| **Một PO cho cả tổ chức bất kể sản phẩm** | Mọi ứng dụng độc lập đều xếp vào một hàng đợi. | Quyết định rối và không còn gắn Product Goal cụ thể. | Xác định ranh giới sản phẩm trước khi quyết định backlog. |
| **PO của từng team có thứ tự riêng cho cùng một sản phẩm** | Các yêu cầu chéo liên tục tranh chấp quyền ưu tiên. | Mất trách nhiệm thống nhất và khó minh bạch mục tiêu. | Làm rõ trách nhiệm Product Owner duy nhất trong Scrum cùng sản phẩm. |
| **Chia việc thuần theo tầng kỹ thuật** | Nhóm UI làm mọi màn hình, backend làm mọi API. | Tích hợp muộn, phát hiện sai yêu cầu ở cuối. | Cắt theo hành vi giá trị và phối hợp liên chức năng sớm. |
| **Đánh dấu Done khi task nhóm xong** | UI mock đã chạy nhưng API thật chưa an toàn. | Báo cáo phần trăm Done ảo, không có Increment. | Tiêu chí tích hợp/DoD chung và trạng thái PBI thật. |
| **Refinement mọi PBI tương lai quá chi tiết** | Tháng này viết đặc tả cho việc có thể làm năm sau. | Lãng phí, thông tin nhanh lỗi thời. | Làm rõ dần theo thứ tự và độ bất định. |
| **Tổng hợp story points nhiều team** | A 20, B 30 → sản phẩm “50 points/tuần”. | Dự báo không có đơn vị nhất quán. | Dùng dữ liệu flow và dự báo theo năng lực/phụ thuộc phù hợp. |
| **Ưu tiên theo số phiếu stakeholder** | Ai nhiều người ủng hộ nhất lên đầu. | Nhu cầu ít người nhưng rủi ro cao bị bỏ qua. | Giá trị, rủi ro, bằng chứng và chi phí cơ hội là căn cứ. |
| **Ưu tiên theo điểm số mà bỏ an toàn** | Lỗi bảo mật điểm Reach thấp nên chờ. | Thiệt hại và vi phạm chuẩn bắt buộc. | Triage sự cố/nghĩa vụ riêng; điểm chỉ hỗ trợ so các lựa chọn phù hợp. |
| **Coi spike là feature đã giao** | Khảo sát API xong được tính như hành vi người dùng đã dùng được. | Output kỹ thuật bị nhầm outcome. | Công khai đầu ra kiến thức và phần phát triển/kiểm chứng còn thiếu. |
| **Mở WIP theo mọi team rảnh** | Ai rảnh bắt đầu ticket mới dù PBI cũ đang chờ tích hợp. | Nhiều hạng mục dở, cycle time tăng. | Ưu tiên hoàn tất, giảm blocked, quản lý WIP qua ranh giới nhóm. |
| **Che phụ thuộc bằng nhãn “Blocked by Team B”** | Có cờ đỏ nhưng không có quyết định, owner hay hạn xử lý. | Trạng thái không giúp giải quyết. | Nêu điều kiện chặn, người phối hợp, bước kế và thời điểm xem lại. |
| **Dùng họp dài thay hợp đồng rõ** | Họp liên nhóm liên tục để diễn giải API. | Tốn phối hợp, vẫn lỗi khi tích hợp. | Ví dụ nghiệp vụ, contract tests, trách nhiệm rõ và trao đổi đúng người. |
| **Big-bang integration ở cuối quý** | Mỗi team chạy tốt ở môi trường riêng. | Rủi ro phát hiện muộn, khó giao giá trị sớm. | CI, kiểm thử tích hợp và lát cắt nhỏ thường xuyên. |
| **Đổi thứ tự theo người hét to** | Stakeholder tự chèn ticket vào Sprint mỗi ngày. | Đứt Sprint Goal, tăng chuyển ngữ cảnh. | Intake/triage minh bạch, đường sự cố riêng, thảo luận đánh đổi. |
| **Ép giữ deadline bằng cách hạ DoD** | Bỏ test retry vì muốn trình diễn đúng ngày. | Lỗi dữ liệu/niềm tin làm chi phí lớn hơn. | Giảm phạm vi, cập nhật dự báo, không bỏ điều kiện an toàn. |
| **Dashboard xanh nhưng người dùng chưa nhận giá trị** | Mỗi team 100% utilization, feature chưa tích hợp. | Tối ưu cục bộ, mất outcome. | Đo theo Product Goal, flow end-to-end và chất lượng. |

### 19.1. Một Product Backlog chung không nên trở thành cơ chế duyệt vi mô

Nếu Product Owner phải ký tên từng task refactor hoặc quyết định tên class, Product Backlog có thể trở thành nút thắt kỹ thuật. Product Owner có trách nhiệm **tối đa hóa giá trị và thứ tự công việc sản phẩm**; Developers cần khả năng thiết kế/cập nhật kế hoạch và giữ chất lượng.

Một cuộc trao đổi tốt có thể là:

> “Hạng mục tra cứu trạng thái là ưu tiên tiếp theo. Chúng tôi cần một thay đổi kỹ thuật ở contract để xử lý Unknown an toàn; nó là điều kiện của lát cắt này. Phạm vi/dự báo sẽ được cập nhật sau khi spike đối tác trả kết quả.”

Điều này làm rõ tác động với sản phẩm mà không yêu cầu Product Owner quyết định từng chi tiết code.

### 19.2. Công việc của chuyên gia kỹ thuật cũng phải có đường nhìn toàn sản phẩm

Nếu nhóm hạ tầng cần cải thiện CI vì mọi PBI đang chờ kiểm thử, không nhất thiết ép mô tả “Là người dùng, tôi muốn chạy build”. Có thể ghi:

- **Vấn đề:** Kiểm thử tích hợp thường chờ môi trường, làm tăng cycle time.
- **Bằng chứng:** Blocked duration và lỗi môi trường lặp nhiều kỳ.
- **Lợi ích:** Giảm thời gian chờ và tăng độ tin cậy của kiểm chứng.
- **Phạm vi nhỏ:** Fixture và quy tắc CI cho một luồng đặt lịch.
- **Tiêu chí:** Thời gian chờ giảm mà test/quality không xấu đi.

Product Owner và Developers có thể cân bằng hạng mục này với feature vì nó **mở khóa khả năng giao giá trị**. Không cần giả vờ đây là một màn hình khách nhìn thấy.

### 19.3. Không so sánh velocity của team như bảng xếp hạng

Nhóm A làm UI, nhóm B bảo vệ giao dịch và nhóm C thử API đối tác. Việc A “đóng nhiều điểm” không chứng minh A hiệu quả hơn B. Story points và velocity, nếu dùng, là công cụ lập kế hoạch **trong bối cảnh riêng**, không phải KPI chuẩn để so người hoặc nhóm.

Nên hỏi **sản phẩm đã tiến tới Product Goal bao nhiêu, nút thắt nào giảm và người dùng có nhận giá trị an toàn không**. Một nhóm tìm ra API không hỗ trợ cách retry đã giả định có thể **tiết kiệm nhiều tuần xây sai**, dù không tăng số story points hoàn tất.

## 20. Bài tập tình huống và đáp án định hướng

### Tình huống A — Ba team, ba ưu tiên số một

Nhóm A ưu tiên thêm giao diện đổi lịch, B ưu tiên refactor transaction, C ưu tiên tích hợp SMS. Product Goal hiện tại là giúp khách **đặt lịch đáng tin và xác định được trạng thái**. Một kiểm thử vừa phát hiện retry có thể tạo lịch trùng.

**Câu hỏi:**

1. Điều gì sai nếu chỉ nhìn từng backlog?
2. Vấn đề nào cần triage an toàn ngay?
3. Một thứ tự Product Backlog hợp lý ban đầu là gì?
4. Có thể để A/C làm gì mà không mở thêm WIP vô nghĩa?

**Hướng giải:** Các nhóm thiếu thứ tự giá trị chung. Lỗi tạo trùng cần được phân loại/khắc phục theo mức nghiêm trọng. Sau đó xác minh API retry/trạng thái, tạo lát cắt tra cứu và trải nghiệm rõ; SMS phải có bằng chứng giá trị. A có thể thử UI có dữ liệu giả đúng contract, C có thể khảo sát API đối tác và hỗ trợ test, nhưng cả hai cần phối hợp với B để tạo Increment tích hợp.

### Tình huống B — “Product” được định nghĩa bằng sơ đồ tổ chức

Một công ty có hai đội làm ứng dụng đặt lịch cho người tiêu dùng và một đội làm sản phẩm kế toán bán độc lập. Quản lý yêu cầu cả ba dùng một Product Backlog vì “cùng công ty”.

**Câu hỏi:**

1. Có căn cứ để coi đây là một sản phẩm không?
2. Cần hỏi những gì trước khi quyết định?
3. Một cơ chế cấp portfolio có thể khác Product Backlog thế nào?

**Hướng giải:** Cùng công ty không đủ. Xem người dùng, giá trị, Product Goal, cách giao/vận hành và quyền quyết định. Có thể có Product Backlog chung cho các đội cùng làm sản phẩm đặt lịch, và backlog khác cho sản phẩm kế toán. Cấp portfolio có thể quyết định đầu tư **giữa các sản phẩm**, không biến thành nơi quản từng task code.

### Tình huống C — Cộng story points xuyên nhóm

Nhóm A dự kiến 24 story points, B 18 và C 30 trong một Sprint. Một báo cáo ghi “toàn sản phẩm chắc chắn giao 72 points”. Team C dùng thang point khác và phải hỗ trợ hai sự cố API.

**Câu hỏi:**

1. Vì sao phép cộng 72 không đại diện năng lực tương đương?
2. Loại dữ liệu nào hữu ích hơn cho dự báo cấp sản phẩm?
3. Tình trạng sự cố nên xuất hiện ở đâu?

**Hướng giải:** Points tương đối theo nhóm, không có thang chung; nghĩa vụ vận hành làm thay đổi năng lực. Xem throughput/cycle time theo hạng mục có ranh giới thống nhất, phân bố, phụ thuộc và availability thực tế. Sự cố cần đường triage, đồng thời ảnh hưởng tới dự báo và khả năng hoàn tất PBI phải minh bạch.

### Tình huống D — Điểm WSJF cho hạng mục phát triển và khám phá

Một nhóm dùng CoD và Job Size tương đối với các lựa chọn:

| Hạng mục | CoD | Job Size |
| --- | ---: | ---: |
| A — Trải nghiệm tra cứu trạng thái | 18 | 6 |
| B — Spike xác minh retry API | 12 | 2 |
| C — Thêm bộ biểu tượng | 5 | 5 |

**Câu hỏi:**

1. Tính WSJF.
2. Nếu chỉ theo phép tính, thứ tự là gì?
3. Vì sao không thể kết luận B tạo nhiều giá trị người dùng hơn A?

**Đáp án:** A \(18/6=3\); B \(12/2=6\); C \(5/5=1\). Thứ tự theo heuristic là **B, A, C**. B có thể là công việc khám phá **mở khóa** A, không phải tính năng dùng được; điểm dựa trên ước lượng tương đối chưa chứng minh giá trị hoặc thời gian giao chắc chắn.

### Tình huống E — Cùng một PBI nhưng ba trạng thái Done

UI đã merge, Booking API đã có endpoint, Adapter chạy với mock. Hợp đồng thật có thể trả Unknown khi timeout; chưa có test đồng thời. Cả ba team đánh dấu phần mình Done.

**Câu hỏi:**

1. PBI cấp sản phẩm đã Done chưa?
2. Cần tiêu chí và test gì?
3. Làm sao giảm nguy cơ lặp lại?

**Hướng giải:** Chưa đủ căn cứ. Cần hành vi end-to-end đúng với Pending/Unknown, contract tests, xử lý idempotency, test concurrency, quyền truy cập và các yêu cầu DoD chung. Tích hợp/test sớm theo từng lát cắt và trạng thái PBI công khai khác trạng thái task nhóm.

### Tình huống F — Một stakeholder mới đòi ưu tiên cao

Sales đề nghị gửi SMS trước cuối tuần, trong khi nhóm B/C đang giải quyết trạng thái Pending và đối soát. Không có số liệu về khách thực sự cần SMS.

**Câu hỏi:**

1. Đề nghị SMS hiện là nhu cầu hay một giải pháp?
2. Cần bằng chứng nào trước khi đổi thứ tự?
3. Nếu mốc cuối tuần là một yêu cầu hợp đồng thật, phải làm gì?

**Hướng giải:** Đó chủ yếu là đề xuất giải pháp. Làm rõ người dùng, giá trị so với kênh hiện tại, chi phí, quyền riêng tư và tác động tới PBI đang làm. Nếu có nghĩa vụ thật, xác minh thẩm quyền/hạn/phạm vi tối thiểu, thảo luận rủi ro và điều chỉnh kế hoạch minh bạch; không âm thầm hạ DoD.

### Tình huống G — Phụ thuộc kéo dài nhưng không ai giải quyết

Một PBI đổi lịch bị gắn nhãn **Blocked by Team C** suốt hai tuần. Team C nói họ cũng chờ API đối tác. Người quản lý yêu cầu họp tất cả team hai giờ mỗi sáng.

**Câu hỏi:**

1. Thông tin nào đang thiếu trên dependency view?
2. Cuộc họp dài có giải quyết được giới hạn kỹ thuật không?
3. Một cách xử lý hợp lý là gì?

**Hướng giải:** Cần câu hỏi API cụ thể, quyết định bị chặn, người liên hệ đối tác, thời điểm xem lại, phương án giảm phạm vi và kết quả spike. Họp đúng người có thể giúp, nhưng cần điều tra hợp đồng/adapter, test trong sandbox và xem một lát cắt khác có thể tiếp tục mà không giả định sai. Công khai tác động tới thứ tự/dự báo.

### Tình huống H — Độ trễ end-to-end và thời gian xử lý

Một lát cắt đi theo trình tự không chồng lấp: thiết kế 1 ngày, phát triển 3 ngày, chờ review 4 ngày, kiểm thử 2 ngày, chờ release 5 ngày.

**Câu hỏi:**

1. Tổng thời gian từ bắt đầu tới phát hành là bao nhiêu?
2. Tổng thời gian xử lý trực tiếp (không tính các bước chờ) là bao nhiêu?
3. Nếu giảm phát triển 3 xuống 2 ngày, tác động tối đa lên lead time trong mô hình này là bao nhiêu?

**Đáp án:** Lead time \(1+3+4+2+5=15\) ngày; thời gian xử lý \(1+3+2=6\) ngày; nếu chỉ giảm một ngày phát triển và mọi bước khác giữ nguyên, lead time còn **14 ngày**. Bài học là tìm **điểm chờ lớn** có thể có nhiều lợi ích hơn chỉ tối ưu coding.

### Tình huống I — Ba team muốn mỗi team một Sprint Goal giống hệt

Một người đề nghị toàn bộ Scrum Teams dùng đúng cùng câu Sprint Goal “Hoàn thành chức năng đổi lịch”, dù Team A chỉ có khả năng thử giao diện, B đang sửa lỗi chống trùng và C chưa thể truy cập sandbox đối tác.

**Câu hỏi:**

1. Scrum Guide có bắt buộc mỗi Scrum Team phải có cùng Sprint Goal không?
2. Product Goal chung và Sprint Goal của mỗi team nên quan hệ thế nào?
3. Cần điều gì để tránh tất cả cùng nghĩ phần mình đã xong?

**Hướng giải:** Không có quy định Sprint Goal phải giống hệt; các team cùng sản phẩm nên chia sẻ Product Goal, Product Backlog, Product Owner và DoD. Mỗi Scrum Team tạo Sprint Goal phù hợp năng lực và đóng góp vào mục tiêu chung. Hợp đồng, phụ thuộc và Increment tích hợp phải được làm rõ.

### Tình huống J — Thay thứ tự trong Sprint khi có sự cố

Giữa Sprint, hệ thống production tạo lịch trùng và cần ứng cứu. Trước đó nhóm A/B/C đang làm ba PBI khác nhau. Quản lý yêu cầu “không được đổi thứ tự vì đã khóa kế hoạch”.

**Câu hỏi:**

1. Điều gì cần làm ngay?
2. Quyết định backlog và kế hoạch Sprint có thể cần thích ứng thế nào?
3. Có được bỏ kiểm thử chất lượng để giữ số PBI dự kiến hoàn tất không?

**Hướng giải:** Ứng cứu và bảo vệ người dùng theo chính sách. Product Owner và Developers làm rõ ảnh hưởng tới năng lực, PBI, Sprint Goal và forecast; phạm vi có thể được thương lượng phù hợp nhưng không được giảm chất lượng. Trạng thái công việc chưa hoàn tất phải minh bạch, không ghi Done ảo.

### Tình huống K — Một PBI “không tạo giá trị” nhưng giúp nhiều nhóm giao nhanh

Nhóm đề xuất tự động hóa việc tạo dữ liệu test cho luồng đặt lịch. Product Owner lo “đó không phải user story”. Dữ liệu lịch sử cho thấy nhiều PBI của A/B/C đang chờ môi trường trung bình bốn ngày.

**Câu hỏi:**

1. Công việc này có thể xuất hiện minh bạch trong Product Backlog không?
2. Cách mô tả giá trị của nó?
3. Một thử nghiệm nhỏ và guardrail có thể là gì?

**Hướng giải:** Có thể diễn đạt là công việc cải thiện năng lực sản phẩm, gắn với số ngày chờ và việc mở khóa PBI. Thử fixture trong sandbox cho một luồng và đo thời gian blocked/cycle time; guardrails gồm độ tin cậy test, bảo mật dữ liệu và chi phí bảo trì. Không cần ngụy trang thành tính năng người dùng.

### Tình huống L — Product Backlog và roadmap không khớp

Roadmap báo “Quý tới ưu tiên khách tự phục vụ đổi lịch”, nhưng Product Backlog gần nhất lại toàn nội dung SMS và đổi màu dashboard. Không có phản hồi về vì sao đổi hướng.

**Câu hỏi:**

1. Điều này cho thấy nguy cơ gì?
2. Nên kiểm tra các bằng chứng nào?
3. Nếu Product Goal đã đổi, việc truyền đạt nên ra sao?

**Hướng giải:** Có thể thiếu liên kết chiến lược–lựa chọn; nhưng cũng có thể Product Goal được điều chỉnh hợp lý mà roadmap chưa cập nhật. Product Owner cùng stakeholder làm rõ outcome, dữ liệu, rủi ro, năng lực và chi phí cơ hội; cập nhật Product Goal/roadmap/backlog theo trách nhiệm thực, giải thích điều gì đổi và dự báo nào không còn đúng.

## 21. Workshop 75–90 phút: tạo backlog và thứ tự sản phẩm cho nhiều nhóm

### 21.1. Đề bài thực hành

Một nền tảng đặt lịch có ba nhóm:

- **Team A:** Trải nghiệm khách hàng trên web/mobile.
- **Team B:** Booking domain, giao dịch và trạng thái.
- **Team C:** API đối tác, thông báo và tích hợp.

Tình hình:

- Product Goal muốn giảm nhu cầu khách gọi tổng đài khi đặt/đổi lịch.
- Khách nói thông báo Pending không rõ.
- Một số request bị gửi lại khi mạng chậm.
- Hợp đồng API đối tác khi timeout chưa chắc chắn.
- Có đề xuất thêm SMS và self-service đổi lịch.
- Kiểm thử tích hợp thường xuyên chờ dữ liệu và môi trường.
- Các team đều có backlog riêng với quá nhiều mục “High Priority”.

**Nhiệm vụ:** Thiết kế cách nhìn chung ở cấp sản phẩm, thứ tự ưu tiên có căn cứ và một kế hoạch phối hợp tạo **một lát cắt tích hợp an toàn**.

### 21.2. Trình tự tổ chức

| Thời lượng | Hoạt động | Đầu ra mong muốn |
| --- | --- | --- |
| **0–10 phút** | Xác định ranh giới sản phẩm và Product Goal. | Một câu mục tiêu có thể kiểm chứng, người dùng/nhóm cùng tạo kết quả. |
| **10–20 phút** | Gom và phân loại các yêu cầu từ nhiều team. | Một nguồn PBI, loại bỏ item trùng, đường sự cố riêng. |
| **20–35 phút** | Viết lại top items theo vấn đề/kết quả; chia một epic thành lát cắt. | Năm tới tám PBI có giá trị và rủi ro rõ. |
| **35–50 phút** | Thảo luận thứ tự theo giá trị, CoD, bằng chứng, rủi ro, công sức. | Một thứ tự đề xuất và lý do/giả định. |
| **50–65 phút** | Vẽ dependency map và nhận diện điểm chờ năng lực. | PBI bị chặn, hợp đồng cần làm rõ, phương án gối việc. |
| **65–75 phút** | Chọn lát cắt tích hợp sớm, các tiêu chí chấp nhận/DoD và guardrails. | Kế hoạch kiểm chứng được, không tính Done giả. |
| **75–90 phút** | Phản biện, mô phỏng một biến cố và cập nhật forecast. | Phương án xử lý thay đổi khi dữ liệu/năng lực khác dự đoán. |

Với đội nhỏ, có thể rút ngắn. Với sản phẩm có nhiều ràng buộc dữ liệu hoặc pháp lý, cần thêm người có chuyên môn và thẩm quyền phù hợp. Workshop **không được trì hoãn ứng cứu sự cố đang gây hại**.

### 21.3. Mẫu một trang cho quản lý backlog cấp sản phẩm

~~~text
PRODUCT BOUNDARY
  Người dùng / khách hàng:
  Kết quả/dịch vụ cốt lõi:
  Nhóm đang tạo sản phẩm:

PRODUCT GOAL
  Kết quả mong muốn:
  Bằng chứng cho thấy đang tiến tới mục tiêu:

PRODUCT BACKLOG - TOP ITEMS
  ID / Hành vi hoặc kết quả:
  Vấn đề và tác động:
  Bằng chứng, giả định chưa xác minh:
  Lý do thứ tự:
  Tiêu chí chấp nhận và chất lượng:
  Phụ thuộc / người phối hợp:
  Cách chia lát cắt:
  Hướng dự báo / mức bất định:

INTAKE AND RISK
  Đường nhận nhu cầu:
  Trường hợp incident/khẩn:
  Quyền ra quyết định và cách báo thay đổi:

COORDINATION
  Hợp đồng và ví dụ nghiệp vụ chung:
  Cách tích hợp/test sớm:
  Chính sách WIP/blocked:
  Điểm review phụ thuộc:

MEASUREMENT
  Outcome:
  Flow end-to-end:
  Guardrails:
  Dữ liệu thiếu / hạn chế suy luận:

NEXT REVIEW
  Bằng chứng cần bổ sung:
  Ai chịu trách nhiệm:
  Ngày hoặc điều kiện xem lại:
  Quyết định có thể đổi sau khi học:
~~~

### 21.4. Một Product Backlog mẫu được sắp thứ tự

| Thứ tự | PBI hoặc hoạt động | Căn cứ ưu tiên | Phụ thuộc cần tháo |
| ---: | --- | --- | --- |
| **1** | Bảo vệ retry không tạo lịch trùng; test liên quan. | Rủi ro dữ liệu đã xác minh. | Quy tắc giữ chỗ và điểm ghi có thẩm quyền. |
| **2** | Spike hợp đồng trạng thái/timeout đối tác. | Giảm bất định của các lát cắt kế tiếp. | Tài khoản sandbox, người hiểu API. |
| **3** | API tra cứu trạng thái có ngữ nghĩa rõ. | Mở khóa trải nghiệm và hỗ trợ. | Kết quả spike và mô hình Pending/Unknown. |
| **4** | UI giúp khách hiểu và tra cứu trạng thái. | Gắn Product Goal, có phản hồi người dùng. | Contract, accessibility và test tích hợp. |
| **5** | Quan sát tỷ lệ gửi lặp, lỗi và completion. | Học hiệu quả sau giao. | Định nghĩa event, bảo vệ dữ liệu. |
| **6** | Đổi lịch cơ bản trong chính sách rõ. | Tăng self-service, cần chia lát cắt. | Quy tắc hủy/giữ chỗ và tích hợp đối tác. |
| **7** | SMS xác nhận cho nhóm có nhu cầu. | Giá trị chưa được kiểm chứng đầy đủ. | Bằng chứng nhu cầu, chi phí và quyền riêng tư. |

**Có thể có thứ tự khác hợp lý** nếu căn cứ, Product Goal hoặc rủi ro khác. Quan trọng là **giải thích được đánh đổi**, không cần tất cả người tham gia nhất trí tuyệt đối về từng vị trí.

### 21.5. Phản biện bằng một biến cố bất ngờ

Sau workshop, người hướng dẫn đưa ra thẻ:

> “API đối tác không bảo đảm kết quả idempotent khi timeout. Nhà cung cấp chưa có API truy vấn trạng thái. Trong khi đó, Team B mất một tuần năng lực vì ứng cứu production.”

Người học cần:

1. Xem **PBI nào không thể triển khai an toàn như dự kiến**.
2. Đề xuất **giảm phạm vi** hoặc **đổi thiết kế trạng thái/đối soát**.
3. Chỉ ra **việc độc lập nào có thể tiếp tục** mà không làm tăng WIP vô ích.
4. Cập nhật **thứ tự Product Backlog và forecast** theo trách nhiệm thực.
5. Soạn một thông báo ngắn nêu **bằng chứng, lý do, hạng mục bị ảnh hưởng và bước kiểm tra tiếp**.
6. Giữ **Definition of Done và guardrails**, không cho phép thông báo sai Confirmed.

**Đáp án định hướng:** Team C tiếp tục làm rõ khả năng đối soát hoặc phương án nhà cung cấp; Team B ưu tiên ứng cứu và bảo vệ bất biến; Team A có thể thử UX cho trạng thái chưa xác định bằng dữ liệu giả, nhưng PBI tích hợp chưa Done. Product Owner cập nhật thứ tự/dự báo và nói rõ không thể cam kết đổi lịch production trước khi giải quyết đường Unknown an toàn.

### 21.6. Tiêu chí đánh giá bài thực hành

- Có phân biệt **sản phẩm và các nhóm**, không gộp/ tách chỉ vì tổ chức.
- Có **Product Goal** liên hệ tới outcome, không chỉ danh sách tính năng.
- PBI được diễn đạt bằng hành vi, rủi ro hoặc năng lực cần thiết.
- Thứ tự phản ánh **giá trị, an toàn, bằng chứng và chi phí cơ hội**.
- Có cách xử lý incident riêng, không trì hoãn lỗi nghiêm trọng để chấm điểm.
- Phụ thuộc được mô tả bằng **điều kiện chặn và hướng xử lý**, không chỉ tên team bị đổ lỗi.
- Một lát cắt được **tích hợp và kiểm chứng**, không tính task Done thay kết quả sản phẩm.
- Forecast và cách truyền đạt phản ánh **mức bất định**.
- Product Owner/Developers/những người có quyền kỹ thuật và release được phân biệt.
- Có cơ chế học từ outcome/flow/chất lượng rồi điều chỉnh Product Backlog.

## 22. Checklist quản lý thứ tự ưu tiên trên phạm vi sản phẩm

### Xác định sản phẩm và mục tiêu

- [ ] Các nhóm cùng làm **một sản phẩm** đã được xác định theo người dùng/giá trị, không chỉ theo sơ đồ tổ chức.
- [ ] Có Product Goal/định hướng giá trị chung và cách quan sát tiến độ.
- [ ] Product Backlog có thứ tự, được quản lý như nguồn công việc **của sản phẩm**, không phân mảnh thành nhiều ưu tiên mâu thuẫn.
- [ ] Nếu có nhiều board thực thi, chúng liên kết và không tạo bản sao ưu tiên riêng không kiểm soát.
- [ ] Roadmap, Product Backlog và kế hoạch nhóm được phân biệt về mục đích, độ chắc chắn và trách nhiệm.

### Tiếp nhận và làm rõ

- [ ] Có đường nhận nhu cầu mới từ khách, stakeholder, vận hành và Developers.
- [ ] Sự cố nghiêm trọng được triage/ứng cứu đúng mức, không chờ bình chọn backlog.
- [ ] Mỗi PBI quan trọng cho thấy **vấn đề/kết quả, bằng chứng, rủi ro và đối tượng**.
- [ ] Không ép lỗi, discovery và nợ kỹ thuật thành user story giả chỉ để hợp công cụ.
- [ ] Những hạng mục trùng được hợp nhất; ý tưởng chưa có căn cứ được làm rõ hoặc lưu phù hợp.
- [ ] Các PBI gần được refinement vừa đủ; hạng mục xa không bị đặc tả thừa.
- [ ] Các lát cắt có giá trị và tiêu chí chấp nhận được đối chiếu với hành trình người dùng.

### Thứ tự và đánh đổi

- [ ] Có lý do vì sao hạng mục A đứng trước B trong bối cảnh Product Goal.
- [ ] Giá trị, rủi ro, chi phí trì hoãn, mức bất định và công sức đều được cân nhắc.
- [ ] Công cụ điểm số chỉ hỗ trợ thảo luận; không che tiêu chuẩn an toàn/nghĩa vụ bắt buộc.
- [ ] Phụ thuộc và phần việc khám phá mở khóa quyết định quan trọng được nhìn thấy.
- [ ] Công việc hỗ trợ chất lượng/nợ kỹ thuật có giá trị và chi phí cơ hội rõ.
- [ ] Năng lực thực và công việc vận hành được dự trù; không cộng story points của các team như cùng đơn vị.
- [ ] Khi đổi ưu tiên, PBI bị lùi lại và lý do/ảnh hưởng cũng được truyền đạt.

### Phối hợp và tích hợp

- [ ] Có dependency map cho những PBI gần, gồm owner phối hợp và bước tháo chặn.
- [ ] Không khởi động quá nhiều lát cắt cùng cần một nút thắt năng lực.
- [ ] Các nhóm làm rõ trạng thái, dữ liệu, API và bất biến bằng ví dụ/contract tests khi cần.
- [ ] Các hợp đồng được kiểm thử và tích hợp thường xuyên, không đợi cuối quý.
- [ ] Nếu dùng Scrum cho nhiều team cùng sản phẩm: chia sẻ Product Goal, Product Backlog, Product Owner và cùng tuân thủ một DoD.
- [ ] Sprint Backlog và kế hoạch kỹ thuật vẫn thuộc trách nhiệm phù hợp của Developers.
- [ ] PBI không bị tính Done chỉ vì UI mock, endpoint hoặc task một nhóm đã xong.
- [ ] Có đường hỗ trợ ứng cứu, bảo mật, quyền truy cập và phát hành an toàn.

### Đo và cải tiến

- [ ] Outcome của sản phẩm được xem cùng flow và chất lượng, không chỉ số ticket.
- [ ] Cycle time, WIP, throughput, work item age có ranh giới và đơn vị rõ.
- [ ] Blocked và việc còn mở được quan sát, không ẩn khỏi dashboard.
- [ ] Không dùng velocity hoặc số story points để xếp hạng các nhóm khác nhau.
- [ ] Forecast công khai mức bất định, điều kiện phụ thuộc và mốc xem lại.
- [ ] Những giả thuyết bị bác bỏ hoặc feature ít giá trị có thể được gỡ bỏ khỏi backlog.
- [ ] Product Owner, Developers và stakeholder dùng phản hồi thực tế để điều chỉnh quyết định.
- [ ] Cải tiến phối hợp hướng tới **giao lát cắt tích hợp**, không chỉ tăng số cuộc họp.

## 23. Ghi nhớ cốt lõi

Khi **nhiều nhóm cùng phát triển một sản phẩm**, câu hỏi quan trọng không phải “mỗi nhóm đang bận với bao nhiêu ticket?”, mà là:

> **“Trong điều kiện giá trị, rủi ro và năng lực hiện tại, phần công việc nào nên được hoàn tất tiếp theo để toàn sản phẩm tạo ra kết quả hữu ích, có chất lượng và có thể học từ phản hồi?”**

Năm nguyên tắc cần nhớ:

1. **Một mục tiêu sản phẩm dẫn hướng lựa chọn.** Xác định đúng ranh giới sản phẩm và nhìn Product Backlog từ kết quả người dùng, không từ sơ đồ nhóm.
2. **Một nguồn thứ tự rõ, nhiều góc nhìn thực thi khi cần.** Nhiều board không có lỗi nếu Product Backlog và quyền quyết định sản phẩm vẫn nhất quán.
3. **Ưu tiên là đánh đổi minh bạch, không phải bảng nhãn High/Medium/Low.** Giá trị, an toàn, Cost of Delay, bằng chứng, phụ thuộc và năng lực phải được cân bằng.
4. **Giá trị chỉ đến khi lát cắt tích hợp đủ chất lượng.** Task của từng nhóm Done chưa đồng nghĩa Product Backlog Item hoặc Increment Done; hợp đồng, test và Definition of Done là thiết yếu.
5. **Thứ tự phải thích ứng khi học thêm.** Dùng outcome, flow, chất lượng, phản hồi người dùng và rủi ro mới để xem lại Product Backlog và forecast.

**Scrum** cung cấp Product Goal, Product Backlog, trách nhiệm Product Owner, Sprint Goal và Increment; khi nhiều Scrum Team cùng một sản phẩm, họ chia sẻ Product Goal, Product Backlog, Product Owner và cùng Definition of Done. **Kanban** giúp quản lý dòng, WIP và thời gian chờ xuyên nhóm. **XP** góp phần bằng TDD, CI, refactoring và thực hành kỹ thuật giúp thay đổi hợp đồng/tích hợp an toàn.

Mục tiêu cuối cùng không phải biến mọi nhóm thành một hàng người chờ lệnh, mà là **giữ quyết định sản phẩm thống nhất, tạo khả năng cộng tác chủ động và giao giá trị nhỏ có thể kiểm chứng thường xuyên**.

### Tài liệu tham khảo nền tảng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/) — các giá trị Agile, ưu tiên cộng tác và đáp ứng thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html) — giao phần mềm thường xuyên, cộng tác hằng ngày, đơn giản và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html) — Product Goal, Product Backlog, Product Owner, Increment, Definition of Done và các Scrum Team cùng một sản phẩm.
- [The Kanban Guide](https://kanbanguides.org/) — Definition of Workflow, WIP, throughput, cycle time, work item age và cải tiến dòng.
- [Scrum.org — Evidence-Based Management](https://www.scrum.org/resources/evidence-based-management-guide) — dùng bằng chứng giá trị và khả năng tạo giá trị để hỗ trợ quyết định sản phẩm.
- [DORA](https://dora.dev/) — tham khảo năng lực giao thay đổi, độ ổn định và chất lượng vận hành phần mềm.
- Jeff Patton, *User Story Mapping* (2014) — cấu trúc hành trình người dùng và các lát cắt giao giá trị tăng dần.
- Don Reinertsen, *The Principles of Product Development Flow* (2009) — tư duy dòng phát triển sản phẩm, hàng đợi, Cost of Delay và đánh đổi kinh tế.
