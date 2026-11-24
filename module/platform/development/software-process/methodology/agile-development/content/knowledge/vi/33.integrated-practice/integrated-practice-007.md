# Mô phỏng một Sprint với trách nhiệm, sự kiện, tạo tác và cam kết

## 1. Mục tiêu của bài thực hành tổng hợp

Trong các bài học riêng lẻ, có thể dễ nhớ rằng Scrum có ba accountability, năm sự kiện và ba tạo tác. Nhưng khi bắt đầu một Sprint thật, những câu hỏi khó thường không nằm ở việc thuộc tên:

- Product Owner muốn một tính năng mới giữa Sprint thì nhóm xử lý thế nào?
- Developers phát hiện lỗi cấp quyền nghiêm trọng dù phần giao diện đã xong thì story có được gọi là Done không?
- Ai sửa Sprint Backlog, ai sắp thứ tự Product Backlog và ai được xác nhận quy tắc nghiệp vụ?
- Daily Scrum có nên hỏi từng người làm gì hôm qua, hay cùng thay đổi kế hoạch để đạt Sprint Goal?
- Khi Sprint Review diễn ra, phần mềm có phải chờ sự kiện ấy mới được phát hành không?
- Retrospective phải tạo thay đổi cụ thể ra sao thay vì một danh sách lời hứa?

**Bài này mô phỏng một Sprint hai tuần của Scrum Team xây dựng nền tảng học trực tuyến**, từ Product Goal đến Sprint Planning, Daily Scrum, xây Increment, Sprint Review và Sprint Retrospective. Người học sẽ đóng vai, cập nhật các tạo tác ở từng thời điểm, xử lý thông tin mới và giải thích quyết định bằng bằng chứng.

Mục tiêu thực hành là có thể:

1. Phân biệt rõ **Product Owner, Developers, Scrum Master** và trách nhiệm giải trình tương ứng.
2. Sử dụng đúng **Product Backlog, Sprint Backlog, Increment** cùng ba commitment **Product Goal, Sprint Goal, Definition of Done**.
3. Điều hành năm **Scrum events** theo mục đích kiểm tra–thích ứng, không chỉ hoàn thành nghi thức.
4. Tạo và điều chỉnh kế hoạch trong Sprint mà **không đánh đổi quyền truy cập, chất lượng và giá trị người học**.
5. Kết hợp **user story, acceptance criteria, ATDD/XP, CI và đo lường flow** trong một tình huống thực tế.
6. Tự đánh giá Sprint bằng **Increment có thể dùng, bằng chứng người dùng, rủi ro và hành động cải tiến**.

Phạm vi gắn với **AGILE_DEVELOPMENT**: hiểu Agile qua phản hồi sớm, giao tăng dần và liên tục thích ứng; vận dụng user story, backlog, Scrum, Kanban, XP và số liệu luồng công việc theo nhu cầu. **Toàn bộ tên người, số liệu và diễn biến dưới đây đều là giả định giảng dạy**, không phải dữ liệu của một sản phẩm có thật.

> **Kết luận định hướng:** Sprint là một khoảng thời gian có mục tiêu để tạo ít nhất một Increment có giá trị và đạt chuẩn, không phải đợt chạy đua đóng nhiều ticket hoặc cuộc thi ai có velocity cao nhất.

## 2. Bộ quy tắc Scrum cần giữ đúng trước khi mô phỏng

Theo Scrum Guide 2020, Scrum là một **khung làm việc nhẹ** giúp con người, nhóm và tổ chức tạo giá trị bằng giải pháp thích ứng cho vấn đề phức tạp. Nó dựa vào **empiricism** và tư duy Lean: ra quyết định dựa trên điều quan sát được, hạn chế lãng phí và thích ứng.

### Ba trụ cột và năm giá trị

| Thành phần | Ý nghĩa trong Sprint mô phỏng |
| --- | --- |
| **Transparency – Minh bạch** | Mục tiêu, việc đang làm, chất lượng, blocker và kết quả có cùng cách hiểu |
| **Inspection – Kiểm tra** | Thường xuyên nhìn lại Sprint Goal, Increment, backlog và phản hồi |
| **Adaptation – Thích ứng** | Đổi kế hoạch khi thực tế thay đổi thay vì bảo vệ một bản kế hoạch đã lỗi thời |
| **Commitment – Cam kết** | Tập trung làm việc theo mục tiêu và chất lượng chung |
| **Focus – Tập trung** | Ưu tiên lát giá trị có ý nghĩa thay vì mở quá nhiều công việc |
| **Openness – Cởi mở** | Nêu rủi ro, sai sót, thiếu hiểu biết và dữ liệu bất lợi |
| **Respect – Tôn trọng** | Lắng nghe chuyên môn của các vai trò, không công kích người nêu lỗi |
| **Courage – Can đảm** | Từ chối gọi Done một tính năng chưa đạt DoD dù gần deadline |

### Các yếu tố cấu thành

| Nhóm | Thành phần của Scrum | Vai trò trong tình huống |
| --- | --- | --- |
| **Accountabilities** | Product Owner, Developers, Scrum Master | Ai chịu trách nhiệm về giá trị, Increment và hiệu quả Scrum |
| **Events** | Sprint; Sprint Planning; Daily Scrum; Sprint Review; Sprint Retrospective | Các thời điểm chính thức để kiểm tra và thích ứng |
| **Artifacts** | Product Backlog; Sprint Backlog; Increment | Các đối tượng minh bạch để mọi người kiểm tra |
| **Commitments** | Product Goal; Sprint Goal; Definition of Done | Mục tiêu và chuẩn chất lượng mà mỗi artifact hỗ trợ |

**Scrum Team là một nhóm thống nhất**, không chứa các tiểu nhóm hay thứ bậc kiểu “team code” đối lập “team QA”. Nhóm có những kỹ năng khác nhau nhưng cùng tập trung vào một Product Goal.

### Timebox liên quan

| Event | Quy định Scrum Guide | Trong mô phỏng hai tuần |
| --- | --- | --- |
| **Sprint** | Tối đa một tháng; Sprint mới bắt đầu ngay sau Sprint trước | Hai tuần, mười ngày làm việc giả định |
| **Sprint Planning** | Tối đa tám giờ cho Sprint một tháng; ngắn hơn thường phù hợp với Sprint ngắn | Nhóm dành khoảng hai giờ |
| **Daily Scrum** | 15 phút mỗi ngày làm việc, cùng thời gian và địa điểm nhằm giảm phức tạp | Mỗi ngày làm việc, 15 phút tối đa |
| **Sprint Review** | Tối đa bốn giờ cho Sprint một tháng | Khoảng 90 phút ở cuối Sprint |
| **Sprint Retrospective** | Tối đa ba giờ cho Sprint một tháng; kết thúc Sprint | Khoảng 60 phút sau Review |

Các khoảng **hai giờ, 90 phút, 60 phút** chỉ là lựa chọn mô phỏng cho Sprint ngắn, không phải timebox cố định bắt buộc. Scrum Guide không yêu cầu một cuộc họp chuyên biệt tên **Backlog Refinement**: refinement là hoạt động liên tục làm rõ và chia nhỏ Product Backlog Items.

## 3. Nhân vật, trách nhiệm và quyền quyết định

Đặt tình huống tại một Scrum Team duy nhất gồm tám người. Tổ chức còn có bên hỗ trợ học viên, người bảo mật dữ liệu và nhóm vận hành để phối hợp khi cần.

| Nhân vật | Accountability trong Scrum | Vai trò trong mô phỏng |
| --- | --- | --- |
| **Lan – Product Owner** | Tối đa hóa giá trị của sản phẩm; quản lý Product Backlog hiệu quả | Nêu Product Goal, sắp thứ tự PBI, làm rõ quy tắc và thương lượng giá trị/phạm vi |
| **Minh – Scrum Master** | Thiết lập Scrum theo định nghĩa; chịu trách nhiệm về hiệu quả Scrum Team | Hỗ trợ self-management, sự kiện đúng mục đích, tháo trở ngại và cải tiến |
| **An – Developer** | Cùng Developers tạo Increment đạt DoD, lập và thích ứng kế hoạch | Năng lực API/authorization |
| **Bình – Developer** | Như trên | Năng lực UI, khả năng tiếp cận |
| **Chi – Developer** | Như trên | Năng lực kiểm thử và phân tích trường hợp biên |
| **Dũng – Developer** | Như trên | Năng lực dữ liệu, contract/API |
| **Hà – Developer** | Như trên | Năng lực CI/CD và quan sát hệ thống |
| **Khoa – Developer** | Như trên | Năng lực frontend/backend và pairing |

Các tên chuyên môn chỉ mô tả **kỹ năng mạnh**, không tạo một phân cấp trong Scrum. Chi không phải “người ký duyệt chất lượng ở cuối Sprint”, Hà không phải người duy nhất được phép nghĩ về vận hành, và An không độc quyền module API.

### Trách nhiệm giải trình khác phân công task

**Product Owner** có thể nhờ người khác viết PBI hoặc khảo sát người dùng, nhưng vẫn chịu trách nhiệm giải trình về quản lý Product Backlog hiệu quả. **Developers** cùng chịu trách nhiệm về kế hoạch Sprint, chất lượng và Increment; họ có thể chọn ghép cặp, chia việc, đổi thứ tự triển khai trong phạm vi Sprint Goal. **Scrum Master** hỗ trợ Scrum và khả năng cải tiến, không là quản lý dự án nhận status hằng ngày.

### Không nhầm PO với người chốt mọi câu hỏi kỹ thuật

Lan có thẩm quyền xác nhận trải nghiệm cần thiết và quy tắc sản phẩm trong phạm vi được giao. An, Chi, Dũng và đồng đội chọn phương án kỹ thuật đáp ứng quy tắc. Nếu một thay đổi ảnh hưởng tới chính sách dữ liệu hoặc quyền sử dụng nội dung ngoài thẩm quyền nhóm, cần **tham vấn người có quyền quyết định tương ứng**. Scrum accountability không thay thế nghĩa vụ tổ chức hoặc pháp lý.

### Câu hỏi nhập vai

Nếu Khoa phát hiện một test thất bại, ai có quyền bảo “cứ đánh Done”? **Không ai được bỏ Definition of Done bằng quyết định cá nhân.** Developers phải bảo đảm Increment đáp ứng DoD; sự minh bạch về điều chưa đạt là bắt buộc.

## 4. Bối cảnh sản phẩm và vấn đề người dùng

Học viên trên nền tảng học trực tuyến có thể ghi danh khóa, học bài theo thứ tự và quay lại sau vài ngày. Phản hồi hỗ trợ cho thấy một số người **không tìm được bài chưa hoàn thành tiếp theo**, nên phải mở danh sách bài và dò thủ công.

Sản phẩm có ít nhất hai quy tắc:

1. **Khóa tuyến tính:** bài được trình bày theo thứ tự; người học có quyền được tiếp tục từ bài phù hợp với tiến độ.
2. **Khóa cần duyệt:** yêu cầu ghi danh ở trạng thái **PENDING** chưa được cấp quyền truy cập nội dung bị hạn chế; khi đủ điều kiện và chuyển thành **ACTIVE**, quyền mới được cấp theo chính sách.

Đây là **quy tắc giả định cho bài mô phỏng**, không phải chính sách của tất cả nền tảng học.

### Câu hỏi sản phẩm cần giải quyết

> “Làm sao để học viên đã có quyền quay lại khóa tuyến tính, mở đúng bài tiếp theo nhanh và dễ hiểu, trong khi hệ thống vẫn bảo vệ quyền truy cập và tiến độ?”

**Sai hướng:** “Xây AI đề xuất bài học ngay” – đã khóa một giải pháp khi chưa kiểm chứng nhu cầu.

**Hướng có giá trị:** “Giảm sự khó khăn khi tiếp tục học đúng bài” – mở nhiều phương án nhỏ, có thể thử và điều chỉnh.

### Đường cơ sở minh họa

Giả sử trong một khoảng quan sát trước Sprint:

~~~text
Số học viên đủ điều kiện quay lại khóa tuyến tính: 200
Số học viên mở đúng bài tiếp theo trong phiên quay lại: 80

Tỷ lệ quan sát ban đầu = 80 / 200 × 100% = 40%
~~~

Số liệu **chỉ làm bối cảnh cho giả thuyết**, không tự nói nguyên nhân làm 120 người còn lại chưa mở đúng bài. Nhóm có thể cần quan sát UX, quyền truy cập, dữ liệu tiến độ hoặc động lực học. Cần định nghĩa **“đủ điều kiện”**, **“quay lại”**, **“đúng bài”** và cửa sổ đo trước khi so sánh.

## 5. Product Goal – commitment của Product Backlog

Product Owner cùng Scrum Team làm rõ hướng phát triển sản phẩm. Trong mô phỏng:

> **Product Goal:** “Học viên đủ điều kiện của các khóa tuyến tính có thể quay lại và tiếp tục đúng vị trí học một cách đáng tin, không phải dò tìm thủ công và không bị cấp sai quyền truy cập”.

Product Goal mô tả **trạng thái tương lai mong muốn của sản phẩm**, không phải lời hứa một Sprint giải quyết mọi thiết bị, mọi loại khóa và mọi dữ liệu.

### Vì sao Product Goal cần đủ rõ?

- Cho Product Owner lý do **sắp thứ tự Product Backlog**.
- Cho Developers khả năng đề xuất **giải pháp đơn giản hơn** yêu cầu ban đầu.
- Giúp stakeholder đánh giá kết quả và trade-off.
- Tạo liên hệ giữa **Sprint Goal ngắn hạn** và giá trị sản phẩm dài hạn.

### Product Goal không phải metric đơn lẻ

Mục tiêu có thể được kiểm tra bằng **tỷ lệ học viên tiếp tục đúng bài, phản hồi người dùng, lỗi quyền và tính toàn vẹn tiến độ**. Không nên thay Product Goal bằng câu “Tăng số story point mỗi Sprint thêm 20%”.

### Product Goal có thể chưa đạt sau Sprint

Điều bình thường là cần nhiều Sprint để tiến về Product Goal. Sprint đầu có thể chỉ cung cấp **hành trình web cho khóa tuyến tính khi online**, chưa gồm đồng bộ offline hoặc gợi ý AI. Vấn đề là lát ấy **có giá trị, đúng và đạt chuẩn**, chứ không phải đã làm mọi ý tưởng.

## 6. Product Backlog ban đầu: một danh sách được sắp thứ tự

Product Backlog là **danh sách có thứ tự, nổi lên theo hiểu biết mới, gồm những gì cần để cải thiện sản phẩm**. Product Owner chịu trách nhiệm quản lý hiệu quả backlog; Developers chịu trách nhiệm về sizing các PBI khi cần ước lượng.

| Thứ tự minh họa | PBI | Giá trị và phạm vi | Câu hỏi còn mở |
| --- | --- | --- | --- |
| **1** | PB-101: API xác định bài tiếp theo có kiểm tra quyền | Người ACTIVE nhận bài hợp lệ hoặc trạng thái hoàn thành | Trường hợp bài cuối, bài bị ẩn, PENDING gọi trực tiếp |
| **2** | PB-102: Nút “Tiếp tục học” và trạng thái UI | Người học có đường đi rõ ràng từ trang khóa | Trạng thái hết khóa, không có quyền, lỗi mạng |
| **3** | PB-103: Quan sát kết quả pilot | Biết người học có mở đúng bài, theo dữ liệu tối thiểu | Event, cohort, bảo mật, mẫu số |
| **4** | PB-104: Đồng bộ tiến độ offline đa thiết bị | Hành trình rộng hơn ở bước sau | Conflict, offline, khả năng khôi phục |
| **5** | PB-105: Gợi ý lộ trình cá nhân hóa | Giả thuyết giá trị tương lai | Nhu cầu, dữ liệu, độ chính xác, chi phí |

Thứ tự này là **đầu vào giả định của Product Owner** cho Sprint. Nó có thể thay đổi khi kết quả mới xuất hiện; các PBI chưa được chọn không phải cam kết chắc chắn sẽ hoàn thành ở Sprint gần nhất.

### Chuẩn bị PBI với ví dụ cụ thể

PB-101 không nên chỉ có tiêu đề “Làm API next lesson”. Lan, An, Chi và Dũng cần hiểu:

- Một học viên ACTIVE và đã hoàn thành bài đầu sẽ mở bài thứ mấy?
- Nếu khóa không còn bài tiếp theo, hệ thống trả kết quả gì?
- Nếu người gửi request không có quyền hoặc đang PENDING, máy chủ xử lý thế nào?
- Nếu dữ liệu tiến độ không tồn tại hoặc cũ, phản hồi có an toàn không?

Những câu hỏi này giúp Product Backlog Item đủ rõ để lựa chọn và lập kế hoạch **mà không đòi hỏi thiết kế đầy đủ từng dòng code trước Sprint**.

### User story ứng viên

> “Là học viên đã đăng nhập và có quyền của khóa tuyến tính, tôi muốn chọn ‘Tiếp tục học’ để mở đúng bài tiếp theo mà không phải tự tìm”.

User story là **một cách diễn đạt PBI**, không phải yếu tố bắt buộc mà mọi Product Backlog Item phải có. Bug, việc giảm rủi ro hoặc cải tiến kỹ thuật cũng có thể xuất hiện nếu phục vụ sản phẩm.

## 7. Acceptance criteria và Definition of Done khác nhau thế nào?

Đây là phần quan trọng của bài thực hành vì nhiều Sprint trông như hoàn tất nhưng **Increment chưa sẵn sàng sử dụng**.

### Acceptance criteria mô tả hành vi cụ thể

Với PB-101, các ví dụ chấp nhận:

~~~gherkin
Feature: Tiếp tục học cho khóa tuyến tính

  Scenario: Mở bài tiếp theo khi đã hoàn thành bài đầu
    Given học viên có đăng ký ACTIVE của khóa tuyến tính ba bài
    And học viên đã hoàn thành bài thứ nhất
    When học viên yêu cầu tiếp tục học
    Then hệ thống trả bài thứ hai mà học viên có quyền mở

  Scenario: Không còn bài khi đã hoàn thành khóa
    Given học viên ACTIVE đã hoàn thành cả ba bài
    When học viên yêu cầu tiếp tục học
    Then hệ thống trả trạng thái đã hoàn thành khóa
    And không trả một bài thứ tư không tồn tại

  Scenario: Người PENDING thử mở bài bằng API
    Given học viên chỉ có yêu cầu ghi danh trạng thái PENDING
    When học viên gọi trực tiếp API để lấy bài bị hạn chế
    Then hệ thống từ chối cấp nội dung

  Scenario: Người lạ thử lấy tiến độ của học viên khác
    Given người gửi không được phép xem tiến độ của học viên khác
    When người gửi yêu cầu API tiếp tục học cho tài khoản đó
    Then hệ thống không tiết lộ tiến độ hoặc nội dung bị hạn chế
~~~

Đây là ví dụ để **người nghiệp vụ xác nhận**, không phải bộ tiêu chí dùng nguyên xi cho mọi sản phẩm. API có thể trả các mã và cấu trúc phản hồi cụ thể theo hợp đồng đã chốt.

### DoD là chuẩn chung của Increment

Trong mô phỏng, Scrum Team tuân theo **Definition of Done** giả định:

| Điều kiện DoD minh họa | Bằng chứng |
| --- | --- |
| Mã đã tích hợp vào nhánh/chế độ tích hợp theo chính sách nhóm | Build/PR và nhánh tích hợp phù hợp |
| Hành vi chấp nhận được xác minh bằng test ở tầng phù hợp | Acceptance, unit, API/integration tests |
| Không cấp sai quyền học hoặc lộ tiến độ cá nhân | Security/authorization tests theo rủi ro |
| CI kiểm tra bắt buộc xanh, không bỏ qua lỗi nghiêm trọng | Pipeline và quyết định xử lý phù hợp |
| Đáp ứng tiêu chuẩn review, xử lý dữ liệu và vận hành của tổ chức | Review/contract, telemetry và tài liệu cần thiết |
| Không có defect chặn chưa được xử lý theo chính sách | Bản ghi kiểm tra và trạng thái chất lượng |
| Increment có thể sử dụng và tích hợp, không chỉ demo giả lập | Được kiểm tra trong môi trường phù hợp |

DoD hiện hành là **cam kết gắn với Increment**. Nếu tổ chức có chuẩn DoD bắt buộc, Scrum Team không được xây DoD thấp hơn. Nhóm có thể cải tiến chuẩn theo cơ chế phù hợp, nhưng **không hạ thấp chất lượng trong Sprint chỉ vì deadline**.

### Phân biệt ba trạng thái thường bị lẫn

- **Task đã code xong:** mới là hoạt động kỹ thuật đã hoàn thành một phần.
- **PBI đạt DoD:** phần công việc tạo thành Increment sử dụng được với chất lượng chung.
- **Đã phát hành cho cohort:** người dùng mục tiêu có thể tiếp cận; availability có thể khác thời điểm đạt DoD.

Scrum **không yêu cầu chờ Sprint Review mới được phát hành Increment**. Review không phải cổng phê duyệt release.

## 8. Sprint Planning: ba chủ đề tại buổi khởi động

**Sprint Planning** bắt đầu Sprint, với sự cộng tác của toàn Scrum Team. Scrum Guide nêu ba chủ đề: **Why is this Sprint valuable? What can be Done this Sprint? How will the chosen work get done?**

### Chủ đề 1: Vì sao Sprint này có giá trị?

Lan trình bày bối cảnh và Product Goal; nhóm thảo luận việc giảm khó khăn khi tiếp tục học. Mọi người thống nhất Sprint Goal:

> **Sprint Goal:** “Học viên ACTIVE của khóa tuyến tính trên web có thể dùng ‘Tiếp tục học’ để mở đúng bài tiếp theo, với kiểm soát quyền và chất lượng đạt DoD, đủ điều kiện thử trong cohort đã thống nhất”.

Đây là **một mục tiêu thống nhất**, không phải sao chép ba tiêu đề PBI rồi gọi là Goal. Định nghĩa cohort và kênh web làm phạm vi đủ nhỏ, còn điều kiện quyền và DoD bảo vệ chất lượng.

### Chủ đề 2: Có thể làm gì trong Sprint này?

Developers xem năng lực thực tế của nhóm, công việc vận hành, thông tin quá khứ, sự không chắc chắn và các PBI đã làm rõ. Họ lựa chọn:

- **PB-101:** API tiếp tục học đúng bài, đúng quyền.
- **PB-102:** UI nút tiếp tục học, trạng thái hoàn thành và quyền.
- **PB-103:** event quan sát kết quả trong phạm vi dữ liệu được phép.

**PB-104 offline sync** và **PB-105 AI gợi ý** không được chọn. Điều này không phủ nhận giá trị tương lai của chúng, mà giữ Sprint Goal có thể tập trung.

### Chủ đề 3: Làm thế nào tạo được Increment?

Developers xây kế hoạch ban đầu:

1. Làm rõ acceptance examples và bất biến quyền học.
2. Xác minh API/authorization, test từ chối ở máy chủ.
3. Phát triển UI dựa trên hợp đồng API, có trạng thái lỗi/hết khóa.
4. Tích hợp liên tục, review nhỏ và kiểm thử end-to-end trọng yếu.
5. Thiết lập sự kiện đo tối thiểu, bảo vệ dữ liệu.
6. Chuẩn bị feature flag, quan sát và đường dừng pilot.

### Ai ước lượng và ai chốt lượng việc?

Developers chịu trách nhiệm sizing Product Backlog Items và **lựa chọn lượng việc họ tin có thể hoàn tất** dựa trên năng lực hiện có, sau khi làm rõ với Product Owner. Lan **không giao bắt buộc 20 story points**, Minh **không chốt thay kế hoạch kỹ thuật**.

### Đầu ra của Sprint Planning

**Sprint Backlog** gồm Sprint Goal, những PBI được chọn và kế hoạch để giao Increment. Chi tiết kế hoạch **có thể tiếp tục được làm rõ và thay đổi trong Sprint**, không phải hợp đồng đóng băng mười ngày.

## 9. Sprint Backlog – artifact thuộc quyền điều chỉnh của Developers

Sau Planning, bản chụp Sprint Backlog:

~~~text
SPRINT: 10 ngày làm việc, mô phỏng hai tuần
SPRINT GOAL:
  Học viên ACTIVE khóa tuyến tính trên web tiếp tục đúng bài,
  đúng quyền, đạt DoD và sẵn sàng pilot cho cohort hợp lệ.

CHOSEN PBI:
  PB-101 – API chọn bài tiếp theo và kiểm tra quyền
  PB-102 – UI Tiếp tục học / Hoàn thành / Không có quyền
  PB-103 – Quan sát sự kiện mở bài đúng trong phạm vi được phép

INITIAL PLAN:
  - PO + Developers + tester: xác nhận ví dụ chấp nhận
  - API/security tests trước khi xem chức năng đủ an toàn
  - UI + API tích hợp sớm, PR nhỏ, CI chạy thường xuyên
  - Kiểm tra DoD theo từng lát; chuẩn bị feature flag và pilot

RISKS / QUESTIONS:
  - Quy tắc khi học viên PENDING gọi API trực tiếp
  - Thứ tự bài từ dịch vụ nội dung; contract phụ thuộc
  - Event đo cần tránh gửi dữ liệu cá nhân không cần thiết
~~~

### Sprint Backlog không phải danh sách mệnh lệnh

Kế hoạch có thể được Developers cập nhật khi học được điều mới, ví dụ:

- Chuyển người từ PBI mới sang review/test để hoàn tất PBI gần Done.
- Thêm test cho trường hợp âm khi phát hiện lỗ hổng.
- Làm việc trực tiếp với dịch vụ Content để thống nhất contract.
- Thương lượng phạm vi với Product Owner khi không thể đồng thời giữ mục tiêu và mọi ý tưởng phụ.

Không ai nên coi việc đổi Sprint Backlog có căn cứ là **“không tuân thủ cam kết”**. Commitment của Sprint Backlog là **Sprint Goal**, còn kế hoạch là phương tiện thích ứng.

### Sprint Goal vẫn có tính ổn định

Không tùy tiện thay Sprint Goal vì một stakeholder vừa nghĩ ra tính năng mới. Trong Sprint, không thực hiện thay đổi làm **nguy hại Sprint Goal**; chất lượng không được giảm; phạm vi có thể được làm rõ và thương lượng với Product Owner khi có hiểu biết mới.

## 10. Timeline Sprint hai tuần: một hành trình có thông tin mới

Tại đây giả định Sprint có **mười ngày làm việc (D1–D10)**. Daily Scrum được duy trì cho từng ngày làm việc của Sprint theo lịch của Developers; bảng dưới đây chọn **sự kiện đáng chú ý**, không phải kịch bản nói chuyện chính xác của toàn bộ thời gian.

| Ngày | Quan sát hoặc sự kiện chính | Hành động thích ứng | Artifact chịu tác động |
| --- | --- | --- | --- |
| **D1** | Sprint Planning làm rõ mục tiêu và chọn ba PBI | Developers lập kế hoạch tích hợp theo DoD | Sprint Backlog hình thành, Sprint Goal rõ |
| **D2** | Three Amigos thống nhất ví dụ nghiệp vụ; API/UI bắt đầu | Thêm negative tests và chia PR nhỏ | Chi tiết PB-101/102 được làm rõ |
| **D3** | Test API phát hiện người PENDING có thể đọc bài trực tiếp | Không gọi Done; xác minh và ưu tiên quyền | Sprint Backlog thêm việc sửa/test bắt buộc |
| **D4** | Bản sửa chặn quyền ở máy chủ, CI có test từ chối | Review và kiểm tra lại đường truy cập | Bằng chứng DoD của PB-101 được bổ sung |
| **D5** | Stakeholder đề nghị thêm AI gợi ý ngay trong Sprint | PO xem lại giá trị; chưa làm lệch Sprint Goal | Product Backlog được cập nhật ý tưởng |
| **D6** | Dịch vụ Content trả thứ tự bài khác contract giả định | Developers làm rõ hợp đồng, test tích hợp | Sprint Backlog và risk log được điều chỉnh |
| **D7** | PB-101 đạt DoD; PB-102 chờ review | Ưu tiên hoàn tất UI trước khi mở việc mới | Increment có lát API hoàn chỉnh; WIP giảm |
| **D8** | PB-102 đạt DoD; PB-103 kiểm tra event và privacy | Hoàn tất test/telemetry cho pilot | Increment có hành trình web dùng được |
| **D9** | PB-103 đạt DoD; feature flag bật cho cohort hợp lệ | Quan sát tín hiệu và phương án dừng | Increment được sử dụng trước Sprint Review |
| **D10** | Sprint Review xem kết quả, feedback; Retrospective cải tiến | PO điều chỉnh Product Backlog; nhóm chọn action cải tiến | Product Backlog cập nhật, hành động mới rõ |

Đây là một kịch bản **Sprint phần lớn đạt mục tiêu nhưng có rủi ro thật**. Kết quả không được phép tự động “xanh” vì đã tới D10; từng PBI chỉ Done khi có bằng chứng đạt DoD.

### Nhịp kiểm tra không bị giới hạn ở các events

Developers có thể pairing, review, kiểm thử và nói chuyện với Product Owner **bất cứ lúc nào trong Sprint**. Scrum events giúp tạo nhịp kiểm tra–thích ứng, không cấm phối hợp ngoài cuộc họp.

### Sơ đồ khái quát

~~~mermaid
flowchart TD
    PG["Product Goal"] --> PB["Product Backlog được sắp thứ tự"]
    PB --> SP["Sprint Planning: Why / What / How"]
    SP --> SG["Sprint Goal + Sprint Backlog"]
    SG --> DS["Daily Scrum: kiểm tra Goal và điều chỉnh kế hoạch"]
    DS --> DEV["Developers tích hợp, test, review, đạt DoD"]
    DEV --> INC["Increment sử dụng được"]
    INC --> SR["Sprint Review: xem kết quả với stakeholders"]
    SR --> PBU["Product Backlog được thích ứng"]
    PBU --> PB
    INC --> RET["Sprint Retrospective: cải tiến cách làm"]
    RET --> NEXT["Thử action ở Sprint tiếp theo"]
    NEXT --> SP
    DEV -. "Thông tin mới" .-> DS
~~~

Sơ đồ nhấn mạnh quan hệ giữa các artifacts và sự kiện; **Increment có thể được tạo và phát hành trước Review**, không phải chỉ xuất hiện sau cuộc họp cuối Sprint.

## 11. Ngày D1–D2: từ câu chuyện người học tới việc có thể kiểm chứng

Ngay sau Planning, nhóm có một **Product Backlog Item** được hiểu đủ để bắt đầu, nhưng chưa chắc đã liệt kê được mọi trường hợp biên. An, Chi và Lan làm một phiên trao đổi ngắn kiểu **Three Amigos**.

### Ba góc nhìn trong phiên làm rõ

| Góc nhìn | Câu hỏi |
| --- | --- |
| **Business/value – Lan** | Quy tắc học viên đủ điều kiện là gì? Khi hết khóa phải thể hiện thế nào? |
| **Implementation – An/Dũng** | API lấy thứ tự và tiến độ từ đâu? Điều kiện đồng thời, lỗi mạng thế nào? |
| **Testing/risk – Chi** | Nếu PENDING gọi URL trực tiếp? Nếu người khác gửi ID học viên? Nếu bài cuối? |

### Từ trao đổi sang kế hoạch kỹ thuật

Developers quyết định:

- Viết unit tests cho thuật toán chọn bài tiếp theo khi thứ tự cố định.
- Dùng API/integration tests cho **authorization**, vì ẩn nút trên UI không bảo vệ request trực tiếp.
- Có contract tests hoặc xác minh giao thức giữa dịch vụ Course/Content và Progress.
- Chỉ dùng dữ liệu học viên giả lập hoặc đã được phép trong test.
- Chia PR đủ nhỏ để review trước khi toàn bộ UI xong.

### TDD/XP giúp rút ngắn vòng phản hồi

Một vòng **Red–Green–Refactor** minh họa:

1. **Red:** test kỳ vọng trả bài thứ hai khi bài một hoàn tất; test đỏ vì logic chưa có.
2. **Green:** triển khai cách đơn giản nhất đáp ứng hành vi đã chốt.
3. **Refactor:** làm sạch code, giữ kiểm thử xanh và ranh giới thiết kế.

Sau đó nhóm bổ sung trường hợp bài cuối, dữ liệu rỗng, bài không có quyền và race condition ở tầng phù hợp. **Unit test xanh không đồng nghĩa đủ DoD**; những rủi ro tích hợp và quyền ở máy chủ cần bằng chứng riêng.

### Tình huống thảo luận

Nếu Lan nêu “Tôi muốn nút màu xanh dương”, Developers có nên coi đó là yêu cầu bắt buộc? Hãy làm rõ đó là **quy tắc thiết kế thương hiệu, tiêu chuẩn khả năng tiếp cận hay sở thích cá nhân**. Tự quản không có nghĩa từ chối ràng buộc hợp lệ, nhưng cũng không nên biến mọi sở thích thành cổng phê duyệt kỹ thuật.

## 12. Daily Scrum: diễn ra cho Developers, không phải status meeting

Mỗi ngày làm việc của Sprint, Developers sử dụng Daily Scrum **15 phút tối đa** để kiểm tra tiến triển hướng tới Sprint Goal và điều chỉnh Sprint Backlog cho phù hợp.

### Hội thoại không có giá trị

~~~text
Scrum Master: Hôm qua từng bạn làm gì?
An: Em code API; hôm nay code tiếp, không blocker.
Bình: Em làm UI; hôm nay làm UI.
Chi: Em đang test, chờ môi trường.
Scrum Master: Đã đủ status; mọi người cố gắng.
~~~

Cuộc hội thoại này không cho biết **liệu Sprint Goal có nguy cơ không đạt và cần đổi kế hoạch ra sao**.

### Hội thoại có tác dụng

~~~text
An: Sprint Goal cần mở bài đúng quyền. Test API cho PENDING đang đỏ,
    PB-101 chưa đạt DoD, nên ưu tiên của tôi là tái hiện và sửa.

Chi: Tôi có request trực tiếp làm lộ nội dung hạn chế.
     Tôi phối hợp An để xác minh ảnh hưởng và bổ sung test.

Bình: PR UI đã sẵn sàng review nhưng có thể bị ảnh hưởng bởi API.
      Khoa có thể review luồng hết khóa trước khi kéo thêm PBI không?

Khoa: Được. Tôi review phần ấy trước khi bắt đầu task mới.

Dũng: Contract thứ tự bài của Content đang chưa rõ.
      Tôi gửi hai ví dụ, có người đầu mối và mốc phản hồi.

An: Vậy hôm nay ưu tiên quyền, review và xác nhận contract.
    Chúng ta cập nhật Sprint Backlog; phần debug chi tiết làm sau họp.
~~~

### Kết quả cần ghi lên Sprint Backlog

| Vấn đề | Tác động tới mục tiêu | Kế hoạch mới |
| --- | --- | --- |
| PENDING đọc nội dung | Chặn PB-101 đạt DoD | An + Chi tái hiện, chặn sai quyền, test tích hợp |
| PR UI chờ review | Có thể tăng WIP, chậm hoàn tất PB-102 | Khoa review trước khi mở PBI khác |
| Contract Course/Content chưa rõ | Có thể mở sai bài | Dũng liên hệ đúng người với ví dụ cụ thể |

**Daily Scrum không phải thời điểm duy nhất được đổi kế hoạch.** Với lỗ hổng có tác động thực, nhóm xử lý theo quy trình bảo mật/incident ngay khi phát hiện, không đợi đến cuộc họp hôm sau.

### Ai có thể tham gia?

Daily Scrum là sự kiện của Developers. Nếu Product Owner hoặc Scrum Master đang **tích cực làm việc trên Sprint Backlog**, họ tham gia **như Developers**. Không có quy tắc Scrum buộc Scrum Master phải chủ tọa hay Product Owner phải nhận báo cáo tiến độ cá nhân.

## 13. Ngày D3–D4: phát hiện lỗi quyền và lựa chọn hành động

Chi thực hiện test mô phỏng:

~~~text
Given: Học viên đăng nhập, có enrollment PENDING
When:  Gọi trực tiếp API lấy nội dung bài bị hạn chế
Expected: Máy chủ từ chối cấp nội dung
Actual: API trả nội dung do chỉ kiểm tra người dùng đã đăng nhập
~~~

Đây là **sai lệch kiểm soát quyền**, không chỉ một lỗi giao diện. PB-101 chưa thể Done. Nếu cơ chế tương tự đang hiện diện trong production, phải dùng kênh xử lý an toàn/sự cố phù hợp ngay; tình huống mô phỏng giả định lỗi mới phát hiện trong môi trường tích hợp.

### Các lựa chọn được đặt lên bàn

| Phương án | Có nên chọn? | Lý do |
| --- | --- | --- |
| Giữ test đỏ nhưng đánh Done vì UI không hiện nút | **Không** | API trực tiếp vẫn truy cập được; vi phạm DoD và quy tắc quyền |
| Bỏ test quyền để tăng velocity | **Không** | Không giải quyết lỗi, tạo báo cáo giả |
| Chặn quyền ở máy chủ và bổ sung negative integration tests | **Có, trong giả định** | Đưa hành vi phù hợp quy tắc đã xác nhận vào Increment |
| Dừng toàn bộ công việc mãi mãi chờ một người quản lý | **Không mặc định** | Nếu nhóm có quyền sửa trong chính sách thì chủ động sửa, chỉ nâng cấp khi vượt thẩm quyền |
| Giới hạn hoặc dừng rollout khi rủi ro ảnh hưởng người dùng | **Có khi cần** | Bảo vệ người dùng và dữ liệu theo quy trình hiện hành |

### Hành động của các accountabilities

- **Developers:** tái hiện, sửa, test, review và điều chỉnh Sprint Backlog để bảo vệ Sprint Goal.
- **Product Owner:** xác nhận quy tắc nghiệp vụ khi còn mơ hồ; minh bạch tác động tới phạm vi và người dùng.
- **Scrum Master:** hỗ trợ nhóm tự quản, loại bỏ trở ngại tổ chức và tránh áp lực “đánh Done cho đẹp”.
- **Người có thẩm quyền bảo mật/vận hành:** tham gia nếu xử lý tác động hoặc ngoại lệ chính sách vượt quyền của Scrum Team.

### Điều gì là Increment ở D4?

Mã có thể đã chạy qua CI sau sửa nhưng **chỉ phần được tích hợp và đáp ứng toàn bộ DoD** mới là Increment sử dụng được. Nếu PB-101 vẫn thiếu contract test bắt buộc, nó chưa được đánh Done dù unit và API tests đã xanh.

## 14. Ngày D5: yêu cầu mới xuất hiện giữa Sprint

Stakeholder kinh doanh nhắn Lan:

> “Học viên muốn AI gợi ý bài học. Chúng ta thêm ngay vào Sprint này để kịp sự kiện giới thiệu.”

Đây là lúc mô phỏng **khả năng thích ứng có định hướng**, không phải bảo vệ mù quáng kế hoạch ban đầu hoặc chấp nhận mọi yêu cầu.

### Quy trình xử lý hợp lý

1. **Product Owner làm rõ giá trị và mức khẩn:** đây là phản hồi người dùng hay ý tưởng mới?
2. **Developers xem tác động tới Sprint Goal, năng lực, DoD, dữ liệu và rủi ro.**
3. Nếu không phục vụ mục tiêu Sprint hiện tại, **Product Owner đưa ý tưởng vào Product Backlog và sắp thứ tự phù hợp**.
4. Nếu thông tin mới đòi điều chỉnh phạm vi PBI đã chọn, Developers trao đổi với PO để **thương lượng phạm vi mà không làm mất Sprint Goal**.
5. Nếu yêu cầu vi phạm ràng buộc dữ liệu hoặc ngoài thẩm quyền, **không tự triển khai chỉ vì đã được yêu cầu**.

### Kết quả trong kịch bản

Lan ghi thêm câu hỏi discovery cho **PB-105**: học viên có vấn đề tìm bài hay cần lộ trình cá nhân hóa? Nhóm **không kéo PB-105 vào Sprint**, vì đang tập trung tạo luồng “Tiếp tục học” đúng quyền, có thể dùng và đo được.

### Tránh hai cực đoan

- **Đóng băng toàn bộ phạm vi:** “Đã Planning thì không được thay bất cứ việc gì” – không phù hợp tính thích ứng của Sprint Backlog.
- **Nhận mọi thay đổi:** “Agile linh hoạt nên đưa bất kỳ ý tưởng nào vào ngay” – phá tập trung và giảm khả năng giao Increment.

### Nếu Sprint Goal thật sự trở nên lỗi thời?

Theo Scrum, **Product Owner là người có thẩm quyền hủy Sprint nếu Sprint Goal trở nên lỗi thời**. Hủy Sprint là lựa chọn đặc biệt, không phải cách thường ngày để tránh khó khăn kỹ thuật hay thay deadline. Tình huống mô phỏng chưa có bằng chứng Goal lỗi thời, nên Sprint vẫn tiếp tục.

## 15. Ngày D6: phụ thuộc hợp đồng API khiến Sprint Backlog thay đổi

Dũng phát hiện dịch vụ Content trả bài theo **thứ tự hiển thị mới**, trong khi API “Tiếp tục học” đang giả định số thứ tự tăng liên tục. Nếu giữ giả định cũ, hệ thống có thể mở sai bài khi bài bị ẩn hoặc chuyển vị trí.

### Điều nhóm cần xác minh

- **Nguồn sự thật** về thứ tự bài là gì?
- Có trạng thái bài bị ẩn hoặc chưa phát hành không?
- Người học đã hoàn thành bài trước khi thứ tự đổi sẽ tiếp tục ở đâu?
- Bên cung cấp và bên tiêu thụ API hiểu cùng hợp đồng không?
- Những trường hợp này có nằm trong phạm vi khóa tuyến tính của Sprint không?

### Bản ghi phụ thuộc ngắn

~~~text
PBI: PB-101 – Xác định bài tiếp theo
Blocker: Cách diễn giải thứ tự bài của Content Service chưa thống nhất
Tác động: Có nguy cơ mở sai bài và không đáp ứng acceptance criteria
Người theo dõi: Dũng
Đầu mối phối hợp: Đại diện Content Service
Bằng chứng cần có: Ví dụ API với bài bị ẩn, đổi thứ tự và bài cuối
Kế hoạch tiếp: Xác nhận contract, viết integration/contract tests
Escalation: Nếu không có quyết định trước thời điểm tích hợp cần thiết
~~~

### Hành động đúng của Developers

Developers có thể điều chỉnh kế hoạch: ưu tiên contract test, ghép người liên quan, thu hẹp **phạm vi đã xác nhận** để không hứa hỗ trợ trường hợp chưa hiểu. Khi điều chỉnh ảnh hưởng hành vi sản phẩm hoặc khả năng đạt Sprint Goal, trao đổi với Product Owner.

Không nên để Dũng báo “đang chờ team khác” trong năm Daily Scrum liên tiếp mà không có owner, thời hạn hoặc lựa chọn an toàn.

### Scrum Master làm gì?

Minh có thể hỗ trợ tạo điều kiện phối hợp hoặc tháo một trở ngại tổ chức, nhưng không **quyết thay** contract nghiệp vụ hoặc thiết kế kỹ thuật. Nếu các nhóm ngoài Scrum Team phải tham gia, việc cộng tác không làm thay đổi accountability của Scrum Team.

## 16. Ngày D7–D8: hội tụ về Increment thay vì mở thêm việc mới

PB-101 đạt DoD sau khi quyền, thứ tự bài và hợp đồng liên quan được kiểm chứng. PB-102 còn một PR chờ review và test trạng thái hoàn tất. PB-103 bắt đầu instrumentation có phạm vi hạn chế.

### Một lựa chọn dựa trên flow

| Cách làm | Hệ quả có thể |
| --- | --- |
| Bình mở thêm PBI mới vì đã code xong UI | Tăng WIP trong khi UI chưa đạt DoD |
| Khoa hỗ trợ review PB-102 và Chi test cùng Bình | Giúp PBI gần Done hoàn tất, giảm hàng đợi |
| Hà chỉ tập trung đo số commit | Không chứng minh Increment đã có giá trị |
| Nhóm ưu tiên fix CI đỏ và test quyền | Bảo vệ chất lượng và khả năng tích hợp |

Nhóm chọn **hoàn tất trước khi bắt đầu thêm**, theo tư duy Kanban/Lean; không phải Scrum bắt buộc mọi nhóm có cùng WIP limit.

### “Done” được đánh khi nào?

Giả sử PB-102 qua review, UI hỗ trợ màn hình hết khóa, ngăn điều hướng khi không có quyền, test tích hợp phù hợp và CI đạt yêu cầu. Nếu toàn bộ DoD đã thỏa mãn, nó có thể được đánh Done. Nếu vẫn thiếu kiểm thử hoặc còn lỗi chặn, **không đổi trạng thái chỉ để khớp báo cáo Sprint**.

### Một Increment có thể hình thành nhiều lần

Scrum cho phép tạo **nhiều Increment trong một Sprint**; chúng cộng dồn vào những Increment trước và phải được xác minh, hoạt động cùng nhau. Không có quy tắc “chỉ khi toàn bộ các PBI Sprint xong mới tồn tại Increment đầu tiên”.

Ví dụ PB-101 có thể trở thành một Increment nhỏ đã tích hợp và đạt DoD. Khi PB-102 đạt DoD, hành trình web có giá trị rõ hơn. PB-103 thêm khả năng quan sát được quyền sử dụng phù hợp. Cần bảo đảm **không có phần phụ thuộc chưa hoàn tất làm Increment được gọi Done khi chưa thể dùng**.

## 17. Ngày D9: giao sớm và quan sát pilot trong guardrails

Sau khi PB-101 và PB-102 đạt DoD, PB-103 cũng được xác nhận đạt DoD với event dữ liệu tối thiểu. Scrum Team có thể đề nghị bật feature flag cho **cohort hợp lệ** theo quyền vận hành đã thống nhất.

### Điều kiện pilot minh họa

| Nhóm điều kiện | Ví dụ kiểm tra |
| --- | --- |
| **Quyền truy cập** | API không cấp bài hạn chế cho PENDING hay tài khoản trái quyền |
| **Chức năng** | ACTIVE tiếp tục đúng bài, bài cuối hiện hoàn thành |
| **Chất lượng** | Increment đạt DoD và CI/integration tests phù hợp |
| **Dữ liệu** | Event đo không thu thông tin cá nhân ngoài phạm vi được phép |
| **Vận hành** | Có telemetry, người theo dõi và phương án dừng feature flag |
| **Phạm vi** | Chỉ khóa tuyến tính web và cohort đã được chấp thuận |
| **Đường báo lỗi** | Hỗ trợ và Developers biết cách nhận và xử lý feedback |

**Pilot không phải lý do bỏ DoD.** Một prototype dùng nội bộ hoặc spike có thể chưa production-ready, nhưng khi tạo Increment có người dùng thật cần tuân thủ chuẩn và chính sách thích hợp.

### Dữ liệu minh họa từ pilot ngắn

Giả sử trong khoảng quan sát ngắn quanh D9–D10 có:

~~~text
Nhóm đủ điều kiện quay lại trong pilot: 60 học viên
Nhóm mở đúng bài tiếp theo: 33 học viên

Tỷ lệ quan sát pilot = 33 / 60 × 100% = 55%

Baseline minh họa trước Sprint:
80 / 200 × 100% = 40%

Chênh lệch quan sát = 55% - 40% = 15 điểm phần trăm
Tăng tương đối so với baseline = 15 / 40 × 100% = 37,5%
~~~

Đây là dữ liệu **giả định, mẫu nhỏ và cửa sổ ngắn**; không chứng minh tính năng gây ra mức tăng hoặc retention dài hạn đã cải thiện. Cần xem khác biệt cohort, mùa học, thay đổi nội dung, cách đo và những người không đủ điều kiện.

### Vì sao không chờ Sprint Review để release?

**Sprint Review là thời điểm kiểm tra kết quả và thích ứng hướng tiếp theo, không phải cổng bắt buộc để phát hành.** Khi Increment thực sự sử dụng được, đạt DoD và được phép theo chính sách release, việc giao sớm giúp nhận phản hồi có ích trước cuộc họp cuối Sprint.

## 18. Tạo tác trong Sprint thay đổi như thế nào?

Ba tạo tác hỗ trợ minh bạch, mỗi tạo tác có một commitment. Bảng dưới đây mô tả **ảnh chụp qua các giai đoạn**, không phải bộ tài liệu hành chính mới.

| Thời điểm | Product Backlog + Product Goal | Sprint Backlog + Sprint Goal | Increment + DoD |
| --- | --- | --- | --- |
| **Trước Sprint** | Danh sách PBI có thứ tự; Product Goal về tiếp tục học | Chưa có Sprint Backlog của Sprint mới | Các Increment hiện có của sản phẩm |
| **Sau Planning D1** | PBI được làm rõ, còn PB-104/105 ở backlog | Sprint Goal và PB-101/102/103, kế hoạch ban đầu | Chưa buộc phải có Increment mới ngay tại Planning |
| **D3 phát hiện lỗi** | Product Backlog có thể chưa đổi thứ tự | Thêm việc sửa authorization/test vào kế hoạch | PB-101 chưa đạt DoD, không gọi Done |
| **D5 ý tưởng AI** | PO ghi nhận và sắp thứ tự ý tưởng | Không cần phá Sprint Goal vì ý tưởng mới | Chất lượng không được hạ |
| **D6 contract mới** | Có thể bổ sung câu hỏi cho PBI tương lai | Developers điều chỉnh phối hợp và test | Chỉ tính Done khi contract được xác minh theo DoD |
| **D7–D8** | PO tiếp tục refinement | Ưu tiên hoàn tất PB-101/102 | Một hoặc nhiều Increment đạt DoD |
| **D9** | Có dữ liệu pilot ban đầu cho ưu tiên tương lai | Theo dõi những việc còn lại và rủi ro | Increment đã có thể được sử dụng bởi cohort |
| **D10 Review** | Điều chỉnh thứ tự theo phản hồi | Sprint hiện tại gần kết thúc, không biến Review thành Planning mới | Inspect phần mềm thật và bằng chứng |

### Tạo tác nào chứa cái gì?

- **Product Backlog:** tập hợp có thứ tự những gì cần để cải thiện sản phẩm, cùng commitment **Product Goal**.
- **Sprint Backlog:** **Sprint Goal + các PBI được chọn + kế hoạch** giao Increment; commitment là **Sprint Goal**.
- **Increment:** bước tiến cụ thể hướng tới Product Goal, đã tích hợp, sử dụng được và đáp ứng **Definition of Done**.

**Báo cáo bug, bảng WIP, test report, deployment dashboard, decision log** có thể rất hữu ích nhưng không phải ba Scrum artifacts chính thức.

## 19. Sprint Review D10: kiểm tra Increment với người liên quan

Sprint Review là sự kiện để **kiểm tra kết quả của Sprint và xác định những thích ứng tiếp theo**, với sự cộng tác giữa Scrum Team và stakeholders. Nó không chỉ là buổi demo cho người quản lý chấm điểm.

### Một agenda 90 phút minh họa

| Phần | Nội dung | Người tham gia |
| --- | --- | --- |
| **Bối cảnh** | Nhắc Product Goal và Sprint Goal, thay đổi môi trường | PO + Scrum Team + stakeholders |
| **Increment thực** | Trải nghiệm web: ACTIVE tiếp tục bài, hết khóa, PENDING bị từ chối | Developers trình bày và cùng thảo luận |
| **Điều đã/chưa đạt** | PB-101/102/103 đạt DoD, PB-104 chưa chọn, giới hạn cohort | Scrum Team minh bạch |
| **Dữ liệu và phản hồi** | Pilot 33/60 cùng giới hạn; phản hồi hỗ trợ, test và rủi ro | Product Owner, hỗ trợ học viên, stakeholders |
| **Hướng tiếp theo** | Có cần ưu tiên mobile sync, khả năng tiếp cận hoặc UX? | Trao đổi với người liên quan |
| **Kết quả** | Cập nhật Product Backlog và giả thuyết cần học tiếp | PO chịu trách nhiệm về backlog |

### Đoạn hội thoại minh họa

~~~text
Lan – PO: Product Goal là giúp học viên quay lại đúng bài.
           Sprint Goal tập trung khóa tuyến tính trên web.

Chi – Developer: Đây là yêu cầu PENDING gọi API trực tiếp
                 và kết quả hệ thống từ chối cấp nội dung.

Bình – Developer: Đây là luồng ACTIVE mở bài hai và trạng thái
                   hoàn thành khóa khi không còn bài tiếp theo.

Đại diện hỗ trợ: Có học viên dùng thiết bị khác và vẫn thấy tiến độ cũ.
                Đây có phải giới hạn đã biết của cohort hiện tại?

Dũng – Developer: Đúng, offline/multi-device sync chưa thuộc lát Sprint.
                   Cần làm rõ trường hợp sử dụng và rủi ro nhất quán dữ liệu.

Lan – PO: Tôi sẽ cân nhắc ưu tiên PB-104 so với AI gợi ý sau khi
           xem thêm feedback và dữ liệu có phạm vi.
~~~

### Những điều không nên diễn ra tại Review

- Bắt Developers đọc danh sách task cá nhân.
- Trình bày PBI chưa đạt DoD như Increment hoàn tất.
- Dùng tỷ lệ pilot ngắn để tuyên bố chắc chắn đạt Product Goal.
- Chỉ báo cáo số story points và không cho stakeholders góp ý.
- Đợi Review “ký duyệt” rồi mới được gọi Done dù DoD chưa đáp ứng.

### Product Backlog được thích ứng

Ví dụ, sau Review, Lan giữ trọng tâm vào độ tin cậy và ưu tiên **nghiên cứu đồng bộ tiến độ giữa thiết bị** hơn xây hệ thống gợi ý AI chưa được chứng minh nhu cầu. Đây là **quyết định giả định** dựa trên dữ liệu có giới hạn, cần tiếp tục cập nhật.

## 20. Sprint Retrospective D10: cải tiến cách làm có chủ đích

Sprint Retrospective **kết thúc Sprint**. Scrum Team kiểm tra các cá nhân, tương tác, quy trình, công cụ và Definition of Done, cùng xác định cách tăng chất lượng và hiệu quả.

### Đừng biến Retro thành truy lỗi cá nhân

Một cách nói không hữu ích:

> “An là nguyên nhân vì code API thiếu quyền; Sprint sau An phải cẩn thận hơn.”

Cách hỏi giúp học hỏi:

> “Tại sao kiểm thử quyền trực tiếp chưa có trước khi API được tích hợp? Acceptance examples, test data và luồng review nào khiến rủi ro được nhìn thấy muộn?”

Scrum Team vẫn phải chịu trách nhiệm sửa lỗi, nhưng **phân tích cơ chế và phòng ngừa** tạo nhiều giá trị hơn việc chỉ trách một người.

### Ba tín hiệu đáng kiểm tra

| Quan sát | Giả thuyết cơ chế | Cải tiến ứng viên |
| --- | --- | --- |
| Test PENDING được viết sau khi API đã hoàn thành phần lớn | Ví dụ chấp nhận thiếu trường hợp âm | Three Amigos cho PBI liên quan quyền trước In Progress |
| Contract thứ tự bài được hỏi ở D6 | Thiếu ví dụ liên nhóm sớm | Xác nhận contract và tạo test trước khi làm UI phụ thuộc |
| UI chờ review hai ngày | Review không được ưu tiên khi có WIP cao | Hoàn tất PR gần Done trước khi kéo thêm việc |

### Chọn một hành động có thể kiểm chứng

> “Trong Sprint tiếp theo, với mỗi PBI liên quan quyền truy cập, Lan, một Developer và người có góc nhìn kiểm thử thống nhất tối thiểu một ví dụ **được phép** và một ví dụ **bị từ chối** trước khi bắt đầu. Chi theo dõi cùng nhóm; xem lại sau Sprint mức độ phát hiện rủi ro trước code, thời gian chuẩn bị và lỗi còn lọt. Giữ, sửa hoặc bỏ nếu không hữu ích.”

Hành động này có **phạm vi, owner, thời điểm, bằng chứng và guardrail**. Nó không phải khẩu hiệu “Giao tiếp tốt hơn”.

### Cải tiến có thể đưa vào Sprint Backlog mới

Theo Scrum, những cải tiến có tác động lớn nhất nên được giải quyết sớm; nhóm có thể đưa vào Sprint Backlog tiếp theo. Không cần tạo một “dự án chuyển đổi” song song khổng lồ chỉ để cải thiện các thực hành kỹ thuật trong Sprint.

### Những vấn đề nhạy cảm

Retrospective không thay thế kênh xử lý bảo mật, quấy rối hay vi phạm nghiêm trọng. Cần bảo vệ quyền riêng tư và dùng người có thẩm quyền khi phù hợp; không ép cá nhân kể thông tin nhạy cảm trước toàn nhóm.

## 21. Bảng ghép toàn bộ trách nhiệm, sự kiện, tạo tác và cam kết

Đây là bảng dùng để tự kiểm tra xem người học có kết nối được **điều ai chịu trách nhiệm** với **đối tượng nào được kiểm tra và điều chỉnh** hay chưa.

| Tình huống | Accountability chính | Event/hoạt động phù hợp | Artifact/commitment |
| --- | --- | --- | --- |
| Xác định trạng thái sản phẩm mong muốn | PO chịu trách nhiệm giá trị; Scrum Team cùng hiểu | Discovery, refinement, Sprint Review | Product Backlog / Product Goal |
| Sắp thứ tự PBI dựa trên phản hồi người học | PO | Refinement, sau Review hoặc khi cần | Product Backlog / Product Goal |
| Chọn lượng việc khả thi cho Sprint | Developers, cùng Scrum Team làm rõ mục tiêu | Sprint Planning | Sprint Backlog / Sprint Goal |
| Lập kế hoạch cách làm và chia việc | Developers tự quản | Sprint Planning và liên tục trong Sprint | Sprint Backlog / Sprint Goal |
| Phát hiện Sprint Goal có nguy cơ | Developers | Daily Scrum, bất cứ trao đổi cần thiết nào | Sprint Backlog / Sprint Goal |
| Phát hiện test quyền API đỏ | Developers xử lý chất lượng; người bảo mật tham gia nếu cần | Kiểm thử/CI/incident theo mức độ, không đợi event | Increment / DoD |
| Thương lượng phạm vi giữa Sprint | Developers và PO theo accountability | Trao đổi bất cứ lúc nào trong Sprint | Sprint Backlog / Sprint Goal; Product Backlog nếu cần |
| Chứng minh PBI đã hoàn tất chất lượng | Developers | Review/test/CI tích hợp liên tục | Increment / DoD |
| Kiểm tra kết quả với stakeholders | Scrum Team và stakeholders; PO điều chỉnh backlog | Sprint Review | Increment / DoD; Product Backlog / Product Goal |
| Điều chỉnh cách phối hợp và phòng ngừa lỗi | Scrum Team; SM hỗ trợ hiệu quả | Sprint Retrospective | Hành động cải tiến, có thể ảnh hưởng Sprint Backlog sau |
| Lựa chọn áp dụng Scrum đúng mục đích | SM accountable cho hiệu quả/thiết lập Scrum; cả nhóm thực hành | Xuyên suốt các events | Toàn hệ thống Scrum |

### Không dùng bảng để lập hệ thống phê duyệt mới

Bảng minh họa **ai có trách nhiệm và đối tượng cần minh bạch**, không có nghĩa mỗi ô phải được ký bởi một cấp quản lý. Nơi cần quyền quyết định tổ chức về dữ liệu, ngân sách, hợp đồng hoặc an toàn, phải làm rõ riêng theo chính sách.

## 22. Nếu Sprint không đạt hết các PBI đã chọn thì sao?

Scrum không bảo đảm rằng mọi ước tính trong Sprint Planning chắc chắn đúng. Một Sprint có thể gặp dữ liệu mới, sự cố hoặc phụ thuộc ngoài nhóm.

### Một biến thể của kịch bản

Giả sử PB-101 và PB-102 đạt DoD nhưng PB-103 chưa hoàn tất kiểm tra quyền riêng tư của event. PB-103 **không được đánh Done** chỉ vì “analytics là việc nhỏ”. Nó không phải phần Increment mới đã hoàn tất.

### Hành động cần thiết

1. **Minh bạch** những gì đã/ chưa đạt DoD, không chuyển trạng thái cho đẹp.
2. **Kiểm tra Sprint Goal:** PB-101/102 đã tạo hành trình web đúng quyền và đủ điều kiện pilot chưa, hay PB-103 là điều kiện không thể thiếu để gọi kết quả sẵn sàng thử?
3. **Thương lượng phạm vi với PO** nếu thông tin mới khiến Sprint Goal khó đạt, trong ranh giới không giảm chất lượng.
4. **Đưa việc chưa xong trở lại Product Backlog** để Product Owner xem xét và sắp thứ tự phù hợp, không tự động coi như đã cam kết làm đầu Sprint tiếp theo.
5. **Dùng Retrospective** tìm cách cải thiện lập kế hoạch, dữ liệu và phối hợp, không dùng nó để gán nhãn kém năng suất.

### Không dùng phần trăm để che chất lượng

“PB-103 xong 95%” chỉ nói cảm nhận tiến triển, không chứng minh đạt DoD. Với một rủi ro về dữ liệu người học, 5% còn lại có thể là **phần quan trọng nhất**.

### Sprint Goal và PBI khác nhau

Sprint Goal là mục tiêu thống nhất. Một Sprint có thể **không hoàn tất mọi PBI đã dự kiến mà vẫn đạt Sprint Goal**, nếu Increment thực tế đáp ứng mục tiêu và DoD. Ngược lại, nhiều PBI Done không bảo đảm Sprint Goal đạt nếu những PBI ấy không tạo giá trị đã thống nhất.

## 23. Phân biệt ba loại thay đổi trong Sprint

| Loại thay đổi | Ví dụ | Cách xử lý |
| --- | --- | --- |
| **Đổi kế hoạch thực hiện** | Chuyển một Developer sang review để giảm hàng đợi | Developers điều chỉnh Sprint Backlog, không cần PO duyệt từng bước |
| **Làm rõ/thương lượng phạm vi** | Khóa tuyến tính web được hỗ trợ, nhưng offline sync chưa đủ điều kiện | Developers và PO trao đổi để giữ Sprint Goal và tính khả thi |
| **Thông tin làm Sprint Goal lỗi thời** | Chính sách sản phẩm loại bỏ hoàn toàn nhu cầu “Tiếp tục học” của cohort mục tiêu | PO có thẩm quyền hủy Sprint nếu Goal lỗi thời |

### Một thay đổi nghiệp vụ không phải chuyện “tự do kỹ thuật”

Nếu nhóm tự quyết rằng PENDING cũng được xem bài hạn chế vì “giảm ma sát UX”, đó là **đổi chính sách sản phẩm và quyền**, không phải điều chỉnh kỹ thuật trong Sprint Backlog. Cần người có thẩm quyền nghiệp vụ và kiểm soát dữ liệu phù hợp.

### Một bug khẩn cấp không cần chờ Daily Scrum

Nếu production lộ nội dung cho người không có quyền, nhóm phải xử lý theo quy trình ngay, rồi cập nhật Sprint Backlog và trao đổi tác động với PO. Các events không phải rào cản báo sự cố.

### Khi PO muốn thêm PBI mới

Không có quy tắc Sprint biến mọi PBI được chọn thành hợp đồng bất biến. Nhưng cũng không có quy tắc “PO được giao thêm task bất cứ lúc nào”. Hãy xem **Sprint Goal, năng lực, trade-off và quyền tự quản của Developers**.

## 24. Scrum với Kanban, XP và Lean trong cùng một Sprint

Bài mô phỏng sử dụng Scrum làm khung, đồng thời kết hợp các thực hành kỹ thuật và quản lý flow **phục vụ một vấn đề đã quan sát được**.

### Scrum giữ nhịp học và mục tiêu

Product Goal, Sprint Goal và DoD tạo định hướng và chuẩn chất lượng; các events tạo cơ hội kiểm tra–thích ứng theo nhịp. Đây không phải “hệ thống điểm danh”.

### Kanban giúp giảm công việc dở dang

Nhóm có thể hiển thị luồng **Ready → In Progress → Review → Test/Integration → Done** và đặt chính sách rõ. Work Item Age của một PBI chưa xong, WIP ở Review/Test hoặc blocked time giúp Developers thấy **điểm nghẽn đang cản Goal**.

### XP giúp tăng phản hồi kỹ thuật

TDD cho quy tắc chọn bài, CI, kiểm thử API/contract và refactoring có thể giúp bắt lỗi sớm. Pair programming giúp chia sẻ hiểu biết khi nhiều Developers cần hỗ trợ module quyền.

### Lean đặt câu hỏi end-to-end

Nếu viết code nhanh hơn một ngày nhưng phải chờ review năm ngày, tối ưu riêng thời gian code không làm người học có tính năng sớm hơn tương ứng. Giảm batch size, chờ đợi và rework có thể tạo giá trị lớn hơn việc tăng số task bắt đầu.

### Không nhập nhằng khung và thực hành

Sử dụng WIP limit hoặc TDD **không làm Scrum Team mất Scrum**. Ngược lại, dùng vài cuộc họp Scrum nhưng không có Sprint Goal, Increment đạt DoD và accountability đúng không thể được coi là vận hành Scrum đầy đủ.

## 25. Đo flow và chất lượng trong Sprint mà không biến thành KPI cá nhân

Giả sử nhóm theo dõi ba PBI được chọn; chỉ số phải đi kèm **định nghĩa và bối cảnh**.

| Tín hiệu | Cách sử dụng | Rủi ro diễn giải |
| --- | --- | --- |
| **WIP** | Có nhiều việc đang mở và ít việc Done không? | Đếm task con có thể làm số cao giả |
| **Work Item Age** | PBI nào chưa xong đang già? | Không dùng để chỉ trích người giữ thẻ |
| **Cycle time** | Từ lúc bắt đầu theo chính sách → Done mất bao lâu? | Không đồng nhất với request → availability |
| **Throughput** | Số PBI/giá trị hoàn tất theo kỳ | Chênh lệch kích cỡ PBI khiến so giữa Sprint dễ sai |
| **CI latency/flaky tests** | Phản hồi kỹ thuật có đủ nhanh và đáng tin không? | Chạy nhanh không đảm bảo test đúng rủi ro |
| **Escaped defects** | Lỗi nào ảnh hưởng người dùng sau release? | Số báo cáo tăng có thể do phát hiện tốt hơn |
| **Outcome pilot** | Học viên mở đúng bài với mẫu số và cohort rõ? | Không suy nhân quả từ ít quan sát |

### Ví dụ WIP và hoàn tất với ba PBI đã chọn

| Mốc | PB-101 | PB-102 | PB-103 | Số PBI Done |
| --- | --- | --- | --- | ---: |
| D3 | In Progress, test quyền đỏ | In Progress | To Do | 0 |
| D6 | Review/Test sau khi sửa quyền | In Progress | To Do | 0 |
| D7 | Done | Review | In Progress | 1 |
| D8 | Done | Done | Review/Test | 2 |
| D9 | Done | Done | Done | 3 |

Nếu WIP được định nghĩa là số **PBI đã bắt đầu nhưng chưa Done**, các ảnh chụp tương ứng có WIP là **2 ở D3, 2 ở D6, 2 ở D7, 1 ở D8 và 0 ở D9**. Khi đọc biểu đồ từ một board khác, phải xác nhận đơn vị thẻ là **PBI, task hay PR**, không cộng chồng những task con với PBI của chính chúng để suy ra WIP của cùng một luồng.

Không có quy tắc Scrum bắt buộc phải báo “Done = 3”. Trong mô phỏng, kết quả có ý nghĩa là **Increment được tích hợp, có giá trị, đạt DoD và phục vụ Sprint Goal**.

### Chỉ số phải chống lại hành vi làm đẹp

Không dùng velocity hoặc số story point để chấm cá nhân. Không giảm DoD để tăng throughput. Không tính những PBI bị kẹt là “không thuộc mẫu” nếu mục tiêu đo là thời gian chờ; cần nhìn cả work item age.

## 26. Hướng dẫn tổ chức buổi mô phỏng trong lớp hoặc nhóm học

Người học có thể thực hành trong **90–150 phút** hoặc chia thành hai phiên. Đây là thời lượng workshop học tập, **không phải thời lượng thật của Sprint hoặc Scrum events**.

### Chuẩn bị

- Nhóm **5–8 người học**, có thể kiêm vai nếu ít người; giải thích rõ khi kiêm vai.
- Một bộ thẻ nhân vật **PO, Scrum Master, Developers**, và 1–2 người đóng stakeholder.
- Bảng Product Backlog, Sprint Backlog, cột trạng thái và một chỗ ghi Increment/DoD.
- Thẻ sự kiện bất ngờ cho **D3, D5, D6 và D9**.
- Mẫu acceptance criteria, test report giả định, outcome pilot.

### Các vòng diễn tập

| Vòng | Nội dung mô phỏng | Sản phẩm bàn giao của người học |
| --- | --- | --- |
| **A – Khởi động** | Nêu Product Goal, thứ tự Product Backlog và ranh giới quyền | Product Goal/DoD được đọc và hiểu đúng |
| **B – Planning** | Làm rõ Why/What/How và chọn Sprint Goal | Sprint Backlog với các PBI, kế hoạch và rủi ro |
| **C – Daily + điều chỉnh** | Nhận thẻ lỗi quyền, contract, yêu cầu AI | Quyết định và Sprint Backlog cập nhật |
| **D – Increment** | Dùng checklist DoD để phân loại Done/chưa Done | Danh sách Increment hợp lệ, điều chưa hoàn tất |
| **E – Review** | Demo tình huống, đọc feedback và outcome | Product Backlog thích ứng, câu hỏi mới |
| **F – Retro** | Xem cơ chế chậm/lỗi, chọn action có thể kiểm tra | Một hành động cải tiến có owner, mốc và guardrail |

### Phân vai không biến thành “giả Scrum”

Trong lớp có thể giao cho một người đóng QA hoặc vận hành để có phản biện, nhưng khi mô phỏng Scrum **không nên tạo vai QA riêng có quyền ký DoD**. Người có năng lực kiểm thử thuộc Developers nếu đang tạo Increment trong Scrum Team; stakeholder bên ngoài mang góc nhìn nghiệp vụ và ràng buộc.

### Người điều phối nên hỏi

“Quyết định này dựa vào artifact nào, commitment nào và accountability của ai?” là câu hỏi hữu ích hơn “đội vừa chạy đúng nghi thức chưa?”.

## 27. Bộ thẻ tình huống cho người chơi

Các thẻ được phát lần lượt; người chơi không nên đọc trước toàn bộ đáp án.

### Thẻ A – Sau Planning

> Product Owner bảo: “Cần hoàn thành cả năm PBI, vì người dùng cần đủ chức năng”. Developers thấy chỉ ba PBI có thể đạt DoD trong Sprint. Ai quyết định lượng PBI được chọn? Sprint Goal có phải là “Hoàn thành năm ticket” không?

**Điểm cần quan sát:** Developers chọn khả năng thực hiện; Scrum Team cùng xác định Sprint Goal có giá trị, PO chịu trách nhiệm về Product Backlog và giá trị. Không hứa tất cả để làm hài lòng stakeholder.

### Thẻ B – D3, test API đỏ

> Khi PENDING gọi API trực tiếp, backend trả nội dung hạn chế. Một người đề nghị “tạm ẩn nút ở UI rồi release”.

**Điểm cần quan sát:** Không được gọi Done hoặc phát hành phần rủi ro; ứng phó theo mức độ, sửa kiểm tra ở máy chủ, bổ sung test và minh bạch tác động.

### Thẻ C – D5, yêu cầu mới

> Stakeholder muốn thêm AI recommendations vào Sprint vì có sự kiện giới thiệu vào thứ Sáu.

**Điểm cần quan sát:** Đánh giá giá trị, tác động, thẩm quyền và rủi ro; có thể ghi Product Backlog, không tự phá Sprint Goal hoặc quyền dữ liệu.

### Thẻ D – D6, hợp đồng API đổi

> Team Content cho biết số thứ tự bài không phản ánh thứ tự hiển thị khi bài bị ẩn.

**Điểm cần quan sát:** Developers làm rõ contract, tạo test, điều chỉnh kế hoạch và có owner liên nhóm; không im lặng tiếp tục dựa giả định sai.

### Thẻ E – D8, review ùn tắc

> Ba PR đang chờ người review, nhưng một Developer muốn bắt đầu PB-104 vì “rảnh”.

**Điểm cần quan sát:** Hỏi Sprint Goal, WIP và cơ hội hoàn tất PBI gần Done; không dùng “mọi người phải bận” làm chuẩn hiệu quả.

### Thẻ F – D9, outcome đẹp nhưng guardrail xấu

> Pilot có nhiều học viên nhấn “Tiếp tục học”, nhưng telemetry cho thấy một người PENDING được mở bài hạn chế.

**Điểm cần quan sát:** Guardrail an toàn vượt ưu tiên tăng trưởng; giới hạn/dừng rollout, ứng phó, điều tra và sửa theo chính sách, không chờ Review để quyết định.

### Thẻ G – D10, một PBI chưa Done

> PB-103 mới đạt 95% vì event telemetry chưa được xác nhận quyền riêng tư.

**Điểm cần quan sát:** Không tính vào Increment, minh bạch tác động Sprint Goal và Product Backlog. Việc còn lại không tự động “được chuyển và cam kết chắc” sang Sprint sau.

## 28. Chấm kết quả diễn tập bằng bằng chứng, không bằng thuộc tên

Một nhóm học có thể nhớ đủ 3–5–3–3 nhưng vẫn ra quyết định sai khi gặp dữ liệu mới. Nên dùng **rubric** như một cách phản hồi chất lượng thực hành, không phải chấm hiệu quả nhân viên thật.

| Tiêu chí | Chưa đạt | Đang hình thành | Đạt trong tình huống |
| --- | --- | --- | --- |
| **Product Goal/Sprint Goal** | Chỉ nói danh sách task | Có Goal nhưng ít dùng để quyết định | Dùng Goal để ưu tiên và thương lượng phạm vi |
| **Accountabilities** | PO/SM giao mọi task, Developers chỉ báo cáo | Có phân quyền nhưng còn chồng chéo | Quyền quyết định phù hợp và minh bạch |
| **Artifacts + commitments** | Chỉ có bảng ticket | Có backlog/Increment nhưng lẫn Done | Đúng Product/Sprint Backlog, Increment và commitments |
| **Daily Scrum** | Điểm danh và cập nhật status | Có nói blocker nhưng thiếu kế hoạch | Developers kiểm tra Goal và thích ứng Sprint Backlog |
| **Quality/DoD** | Gọi code complete là Done | Có test nhưng thiếu kiểm tra quyền | Increment chỉ Done khi đủ DoD và an toàn |
| **Thích ứng khi có thay đổi** | Nhận mọi yêu cầu hoặc đóng băng mọi việc | Có điều chỉnh nhưng chưa nêu trade-off | Nêu lựa chọn, tác động, thẩm quyền và giữ Goal |
| **Review** | Demo cho sếp xem và chấm điểm | Có feedback nhưng không đổi backlog | Inspect Increment, outcome và điều chỉnh Product Backlog |
| **Retro** | Đổ lỗi cá nhân hoặc khẩu hiệu | Có action nhưng thiếu cách đo | Action có owner, phạm vi, mốc và bằng chứng |

### Một câu hỏi phản tư sau mỗi vòng

> “Nếu người dùng thật nhìn thấy kết quả của quyết định này, điều gì có thể tốt lên, điều gì có thể bị gây hại, và nhóm sẽ **biết bằng cách nào**?”

Scrum không chỉ là quy tắc tổ chức cuộc họp; nó cung cấp khung **học từ thực tế để tạo giá trị trong giới hạn an toàn**.

## 29. Bài tập vận dụng độc lập – 15 câu hỏi

### Bối cảnh bổ sung

Giả sử đến D8 của Sprint mô phỏng:

- PB-101 đã đạt DoD.
- PB-102 đã code xong nhưng chưa chạy test trạng thái không có quyền.
- PB-103 chưa có phê duyệt phù hợp về event chứa định danh người dùng.
- Một stakeholder tuyên bố “KPI tốt là Done 100% story points”.
- Product Owner muốn ưu tiên thêm tính năng “Thông báo học lại” ở Sprint tới.
- Test integration phát hiện Content Service thay thứ tự bài khiến một số trường hợp mở sai bài.

### Câu hỏi

1. Nêu **ba accountabilities** của Scrum và trách nhiệm chính của mỗi bên.
2. Liệt kê **năm Scrum events**, sự kiện nào bao trùm những sự kiện còn lại?
3. Ghép đúng **ba artifacts** với **ba commitments**.
4. Sprint Planning cần trả lời ba chủ đề **Why, What, How** như thế nào?
5. Developers có được đổi Sprint Backlog trong Sprint không; điều kiện quan trọng là gì?
6. Ai chịu trách nhiệm sizing PBI và ai có quyền sắp thứ tự Product Backlog?
7. PB-102 có được đánh Done vì code đã xong không? Vì sao?
8. PB-103 chứa dữ liệu chưa được chấp thuận có được triển khai pilot không?
9. Câu nói “PBI đã hoàn thành 95%” có thay việc đáp ứng DoD không?
10. Khi test integration phát hiện mở sai bài, Daily Scrum nên tạo điều chỉnh gì?
11. Người quản lý muốn xem ngày giao và rủi ro, có phải dự Daily Scrum để từng người báo cáo không?
12. Product Owner có nên thêm ngay “Thông báo học lại” vào Sprint hiện tại không?
13. Một Increment đã đạt DoD có phải chờ Sprint Review mới được phát hành?
14. Nếu PB-102 chưa Done cuối Sprint, nó có tự động trở thành PBI cam kết đầu Sprint sau không?
15. Chọn **một hành động Retrospective** theo vấn đề đã xảy ra và nêu bằng chứng để xem hiệu quả.

## 30. Lời giải tham khảo và cách giải thích

### Câu 1–3: nền tảng Scrum

1. **Product Owner:** tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. **Developers:** tạo Increment sử dụng được, đáp ứng DoD và tự quản kế hoạch Sprint. **Scrum Master:** thiết lập Scrum như được định nghĩa và giúp Scrum Team/tổ chức tăng hiệu quả.
2. Năm events: **Sprint** (bao trùm), **Sprint Planning**, **Daily Scrum**, **Sprint Review**, **Sprint Retrospective**.
3. **Product Backlog ↔ Product Goal; Sprint Backlog ↔ Sprint Goal; Increment ↔ Definition of Done**.

### Câu 4–6: lập kế hoạch và tự quản

4. **Why:** vì sao Sprint có giá trị, đi đến Sprint Goal. **What:** PBI nào có thể Done trong Sprint với năng lực thực. **How:** Developers lên kế hoạch tạo Increment đáp ứng DoD.
5. **Có.** Developers điều chỉnh Sprint Backlog khi học được điều mới, tập trung Sprint Goal; không làm giảm chất lượng, không làm nguy hại mục tiêu, trao đổi phạm vi với PO khi cần.
6. **Developers** chịu trách nhiệm sizing; **Product Owner** chịu trách nhiệm thứ tự và quản lý Product Backlog hiệu quả, có thể tham khảo người liên quan.

### Câu 7–9: chất lượng và dữ liệu

7. **Không.** PB-102 thiếu test về người không có quyền, chưa đáp ứng điều kiện DoD/acceptance liên quan nên chưa Done.
8. **Không trong điều kiện đề bài.** PB-103 phải đáp ứng chính sách dữ liệu và kiểm tra bắt buộc; chỉ triển khai khi đạt điều kiện hợp lệ.
9. **Không.** Phần trăm công việc không thay thế kiểm chứng DoD; 5% còn lại có thể là kiểm soát chất lượng quan trọng nhất.

### Câu 10–12: kiểm tra và thích ứng

10. Developers cần xác định tác động lên Sprint Goal, ưu tiên tái hiện và sửa, phối hợp Content Service để làm rõ contract, bổ sung tests và điều chỉnh Sprint Backlog. Không chờ đến Sprint Review để nói về lỗi có tác động.
11. **Không cần.** Người quản lý có thể dùng board, Increment, rủi ro, dự báo và kênh hỗ trợ phù hợp. Daily Scrum dành cho Developers kiểm tra–thích ứng, không phải buổi status cho cấp trên.
12. **Không tự động.** PO cân nhắc giá trị và Product Backlog; nếu ảnh hưởng Sprint hiện tại phải trao đổi với Developers, bảo vệ Sprint Goal và DoD. Với đề bài, có thể xem ở refinement/Sprint tương lai.

### Câu 13–15: Increment, backlog và cải tiến

13. **Không.** Increment đạt DoD có thể được giao trong Sprint theo chính sách release. Sprint Review không phải gate phát hành.
14. **Không.** Phần việc chưa hoàn tất quay lại Product Backlog để được xem xét và sắp thứ tự; Sprint Planning tiếp theo sẽ lựa chọn dựa trên Goal/năng lực mới.
15. Ví dụ: “Trong Sprint tiếp theo, trước khi bắt đầu PBI liên quan quyền hoặc trạng thái khóa, Developers và PO cùng xác nhận ít nhất một ví dụ được phép và một ví dụ từ chối, gắn test tại tầng API/integration. Chi theo dõi; xem lại số lỗi tìm muộn và thời gian làm rõ, không bỏ DoD. Sau Sprint đánh giá giữ/sửa/dừng”. Đây là action có **người theo dõi, phạm vi, mốc và bằng chứng**.

### Điều quan trọng ở lời giải

Các quyết định đúng không đến từ việc học thuộc từng bước cứng. Người học cần luôn liên kết **giá trị người dùng → Goal → quyền quyết định → DoD → dữ liệu kiểm chứng → thích ứng**.

## 31. Những sai lầm thường gặp khi diễn tập Sprint

| Sai lầm | Vì sao sai hoặc gây hại | Cách thay |
| --- | --- | --- |
| **Sprint Goal là danh sách 10 task** | Không nói được vì sao Sprint có giá trị | Mô tả kết quả thống nhất phục vụ Product Goal |
| **PO giao từng task cho Developers** | Giảm tự quản và chồng chéo accountability | PO làm rõ giá trị, Developers chọn cách thực hiện |
| **SM nhận báo cáo cá nhân hằng ngày** | Daily Scrum thành điểm danh | Developers kiểm tra Sprint Goal và kế hoạch chung |
| **Có ba câu hỏi là tự động đúng Scrum** | Nghi thức không bảo đảm inspection–adaptation | Đo xem kế hoạch có được điều chỉnh khi cần |
| **Mọi PBI chọn ở Planning đều phải hoàn thành bằng mọi giá** | Ép bỏ DoD khi thực tế thay đổi | Minh bạch, thích ứng kế hoạch, giữ Sprint Goal |
| **Tự thay đổi Sprint Goal vì stakeholder mới yêu cầu** | Mất tập trung, không có commitment | PO và Scrum Team đánh giá giá trị; Goal không tùy tiện đổi |
| **Chỉ code xong là Done** | Increment chưa đủ chất lượng | Dựa vào DoD và kiểm thử phù hợp |
| **Giữ test quyền đỏ để kịp deadline** | Có thể cấp nội dung trái phép | Sửa lỗi, thu hẹp phạm vi an toàn hoặc không release |
| **QA ở cuối Sprint mới kiểm thử** | Phản hồi muộn, sửa tốn kém | Chất lượng xuyên Sprint, ATDD/CI/XP |
| **Chờ Sprint Review mới được release** | Chậm học hỏi và tạo gate không bắt buộc | Giao Increment đạt DoD theo chính sách khi sẵn sàng |
| **Sprint Review là buổi đánh giá năng suất nhân viên** | Thiếu phản hồi giá trị, mọi người phòng thủ | Inspect Increment, điều kiện môi trường và backlog |
| **Retrospective chỉ ghi “cố gắng hơn”** | Không có cách kiểm tra tác dụng | Action nhỏ có owner, mốc, outcome/guardrail |
| **Mọi việc chưa Done tự động sang Sprint kế tiếp** | Bỏ qua quyền sắp thứ tự và kế hoạch mới | Đưa về Product Backlog để xem lại |
| **So story points giữa nhóm** | Không có đơn vị chung, gây làm đẹp ước lượng | Dùng dữ liệu trong bối cảnh, theo outcome/flow/quality |
| **Đồng nhất DoD với PO thích demo** | Thiếu chuẩn chung về chất lượng | DoD là commitment của Increment |
| **Gọi mọi thí nghiệm UI là production-ready** | Nhầm prototype/spike với Increment | Chỉ release phần đã đạt DoD/guardrails |
| **Lấy số click pilot làm retention** | Không cùng khái niệm, thiếu mẫu số | Định nghĩa đúng outcome và cửa sổ đo |
| **Mở thêm PBI khi Review ùn tắc** | WIP cao, ít giá trị hoàn tất | Giúp hoàn tất, xem blocker và Sprint Goal |
| **Im lặng khi có rủi ro bảo mật để giữ báo cáo xanh** | Tổn hại người dùng, mất minh bạch | Báo qua kênh incident và xử lý ngay |
| **Bảo rằng “Scrum không cho đổi kế hoạch”** | Nhầm Goal với chi tiết Sprint Backlog | Developers thích ứng kế hoạch hướng tới Goal |

## 32. Mẫu làm bài thực hành một trang

~~~text
TÊN SPRINT / THỜI LƯỢNG:
PRODUCT GOAL:
SPRINT GOAL:
NHÂN VẬT VÀ ACCOUNTABILITIES:
  Product Owner:
  Developers:
  Scrum Master:

PRODUCT BACKLOG (ĐƯỢC SẮP THỨ TỰ):
  1.
  2.
  3.
  Phần chưa chọn:

SPRINT BACKLOG SAU PLANNING:
  PBI được chọn:
  Kế hoạch ban đầu:
  DoD và guardrails:
  Phụ thuộc / câu hỏi còn mở:

DAILY SCRUM / QUYẾT ĐỊNH GIỮA SPRINT:
  Ngày / thông tin mới:
  Tác động Sprint Goal:
  Hành động/owner/mốc:
  Điều chỉnh Sprint Backlog:
  Việc cần PO hoặc bên có thẩm quyền xác nhận:

INCREMENT:
  Phần nào đạt DoD:
  Bằng chứng test/integration/CI:
  Phần chưa Done và lý do:
  Availability / feature flag / cohort nếu có:

SPRINT REVIEW:
  Điều gì đã giao và được kiểm tra:
  Feedback / outcome / giới hạn mẫu:
  Product Backlog cần điều chỉnh:

SPRINT RETROSPECTIVE:
  Quan sát về cách làm:
  Một thử nghiệm cải tiến:
  Owner / khi nào xem lại / cách kiểm tra hiệu quả:
  Guardrails không được đánh đổi:
~~~

### Một bản mô phỏng có chất lượng cần ghi cả điều chưa biết

Nếu người học không biết contract API hoặc chưa được phép dùng dữ liệu, hãy viết **“Chưa biết – ai xác nhận – khi nào cần kết luận”**, thay vì bịa quy tắc để kịch bản đẹp. Tự chủ Agile đòi hỏi **quyết định có bằng chứng và đúng thẩm quyền**, không phải giả vờ chắc chắn.

## 33. Checklist tự đánh giá trước khi kết thúc buổi mô phỏng

- [ ] Có diễn đạt **Product Goal** bằng kết quả người học và gắn đúng Product Backlog?
- [ ] Product Backlog là **danh sách có thứ tự và có thể thay đổi**, không phải hợp đồng cố định?
- [ ] Có phân biệt **Product Owner, Developers, Scrum Master** về accountability?
- [ ] Developers có quyền tự quản **cách làm, phân công và điều chỉnh kế hoạch** trong Sprint?
- [ ] Scrum Team có cùng hiểu biết về **Sprint Goal** và vì sao Sprint có giá trị?
- [ ] Sprint Planning trả lời **Why, What, How**, không chỉ chia task?
- [ ] Sprint Backlog gồm **Goal, các PBI được chọn và kế hoạch** để tạo Increment?
- [ ] Daily Scrum do Developers phục vụ mục đích **kiểm tra Goal và thích ứng kế hoạch**?
- [ ] Daily Scrum có timebox **15 phút** và không bị biến thành báo cáo quản lý?
- [ ] Blocker có người theo dõi, bước tiếp và mốc phản hồi, không chỉ “đang chờ”?
- [ ] Khi API có lỗi quyền, nhóm **không gọi Done hoặc phát hành sai chính sách**?
- [ ] Các điều kiện **PENDING/ACTIVE, quyền đọc dữ liệu và trường hợp biên** được làm rõ?
- [ ] Có dùng test phù hợp: unit, API/integration, contract, CI theo rủi ro?
- [ ] Các PBI hoàn tất đều có **bằng chứng đáp ứng DoD**?
- [ ] Có phân biệt **task code complete, Increment đạt DoD và availability tới người dùng**?
- [ ] Sprint Backlog có được thay đổi khi thông tin mới xuất hiện **mà không phá Sprint Goal**?
- [ ] Khi stakeholder đưa yêu cầu mới, Product Owner và Developers **đánh giá tác động/phạm vi**?
- [ ] Không dùng Agile để tự đổi chính sách dữ liệu hoặc bỏ qua người có thẩm quyền?
- [ ] Khi phụ thuộc liên nhóm xuất hiện, có owner, câu hỏi và đường escalation rõ?
- [ ] Nhóm có nhận diện WIP, Work Item Age và review/test queue khi có dấu hiệu chờ?
- [ ] Increment có thể **được tạo/giao nhiều lần trong Sprint** khi đáp ứng DoD và chính sách?
- [ ] Sprint Review có **Increment thực, feedback và điều chỉnh Product Backlog**, không chỉ slide?
- [ ] Sprint Review **không được xem là cổng bắt buộc** để release hoặc hợp thức hóa PBI chưa Done?
- [ ] Retrospective kết thúc Sprint với **hành động cải tiến cụ thể**, không truy lỗi cá nhân?
- [ ] PBI chưa Done được minh bạch và **không tự động cam kết sang Sprint mới**?
- [ ] Có dùng outcome theo **mẫu số/cohort/cửa sổ đo**, tránh tuyên bố nhân quả từ mẫu nhỏ?
- [ ] Có giữ guardrails về quyền học, dữ liệu, DoD và nhịp làm việc bền vững?
- [ ] Người học có thể giải thích **ai quyết định, bằng chứng gì và artifact nào được điều chỉnh** trong từng tình huống?
- [ ] Có phân biệt Scrum framework với **thực hành bổ trợ Kanban, XP, Lean và ATDD**?
- [ ] Sau Sprint, nhóm hiểu **giá trị đã giao, rủi ro còn lại và thử nghiệm cần làm tiếp**?

**Ghi nhớ:** **Một Sprint không được đánh giá bằng việc thuộc tên các sự kiện hay đóng hết task.** Scrum Team sử dụng **Product Goal để giữ hướng sản phẩm, Sprint Goal để tập trung ngắn hạn và Definition of Done để bảo vệ chất lượng Increment**. Product Owner tối đa hóa giá trị, Developers tự quản cách tạo Increment đạt DoD, Scrum Master giúp Scrum vận hành hiệu quả. Sprint Planning khởi tạo kế hoạch, Daily Scrum giúp điều chỉnh hằng ngày, Sprint Review kiểm tra kết quả với người liên quan, Sprint Retrospective cải thiện cách làm. Khi kết hợp phản hồi sớm, user story rõ, kiểm thử tự động, dòng công việc minh bạch và quản trị rủi ro phù hợp, nhóm mới thật sự **giao giá trị tăng dần và thích ứng có trách nhiệm theo tinh thần Agile**.
