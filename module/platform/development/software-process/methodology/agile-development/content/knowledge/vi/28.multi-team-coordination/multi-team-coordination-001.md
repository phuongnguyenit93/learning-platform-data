# Xác định sản phẩm chung, mục tiêu chung và ranh giới nhóm

Một công ty phát triển nền tảng học trực tuyến có bốn nhóm kỹ thuật: nhóm giao diện, nhóm API, nhóm dữ liệu và nhóm kiểm thử. Người phụ trách từng nhóm đều nói họ đã hoàn thành gần hết việc được giao. Tuy nhiên, học viên vẫn không đăng ký được khóa học trả phí vì giao diện dùng một định nghĩa trạng thái, API dùng định nghĩa khác, dữ liệu giao dịch chờ chuyển đổi, còn kiểm thử đầu-cuối chỉ được chạy sau khi cả bốn nhóm tuyên bố đã “xong phần mình”.

Lãnh đạo quyết định áp dụng Agile và tổ chức Sprint cho cả bốn nhóm. Sau ba Sprint, dashboard của từng nhóm đẹp hơn, nhưng khả năng **“học viên thanh toán hợp lệ và vào bài đầu”** vẫn chưa hoạt động đáng tin. Vấn đề không chỉ là thiếu một cuộc họp liên nhóm. Các bên chưa thống nhất:

- **Sản phẩm chung là gì** và đâu là ranh giới giá trị mà học viên nhận được?
- **Mục tiêu chung** nào quan trọng hơn việc mỗi nhóm hoàn thành một danh sách task?
- **Nhóm nào chịu trách nhiệm từ đầu đến cuối** cho phần giá trị có thể kiểm chứng?
- **Ai có quyền ưu tiên công việc**, nhất là khi nhóm giao diện, API, dữ liệu và kiểm thử có các yêu cầu cạnh tranh?
- **Khi nào một Increment thực sự Done** nếu mỗi nhóm có định nghĩa hoàn tất khác nhau?

Phối hợp nhiều nhóm trong Agile bắt đầu từ **sản phẩm và dòng giá trị**, rồi mới thiết kế ranh giới nhóm, quyền quyết định, backlog, cơ chế tích hợp và nhịp trao đổi. Nếu làm ngược lại — giữ nguyên sơ đồ tổ chức rồi chỉ thêm Sprint hoặc cuộc họp — có thể tạo ra nhiều nhóm bận rộn nhưng ít khả năng hoạt động hoàn chỉnh.

Bài thuộc chương **Phối hợp nhiều nhóm** của module **AGILE_DEVELOPMENT**. Nội dung liên kết giá trị và nguyên tắc Agile, phản hồi sớm, giao sản phẩm tăng dần, user story, backlog, Scrum, Kanban, XP và các số đo dòng công việc để lựa chọn cách hợp tác phù hợp khi **nhiều nhóm cùng đóng góp cho một hoặc nhiều sản phẩm**.

> **Thông điệp cốt lõi:** Không bắt đầu bằng câu “có bao nhiêu đội và mỗi đội làm công nghệ gì?”. Hãy bắt đầu bằng “người dùng cần kết quả nào, phần nào cùng tạo ra sản phẩm đó, ai quyết định ưu tiên và chúng ta tổ chức đội ra sao để giao giá trị tích hợp với ít bàn giao nhất?”.

## Mục tiêu học tập

Sau bài này, bạn có thể:

1. Phân biệt **sản phẩm (product)**, **thành phần kỹ thuật (component)**, **nền tảng dùng chung (platform)**, **dự án (project)**, **dịch vụ (service)** và **nhóm phát triển (team)**.
2. Nhận diện khi nào nhiều nhóm thực sự **cùng phát triển một sản phẩm**, khi nào họ sở hữu **những sản phẩm/dịch vụ khác nhau có phụ thuộc**, và vì sao không thể quyết định chỉ từ số repository hoặc sơ đồ phòng ban.
3. Xác định **người dùng, kết quả mong đợi, Product Goal, phạm vi sản phẩm, Product Backlog, Product Owner và Definition of Done** rõ ràng trong bối cảnh Scrum nhiều nhóm.
4. Hiểu ranh giới **cross-functional, self-managing**, năng lực end-to-end, phụ thuộc và chi phí nhận thức của nhóm; phân biệt team boundary với code ownership.
5. Thiết kế cơ chế phối hợp có ích: ưu tiên chung, refinement xuyên nhóm, lát cắt dọc, tiêu chuẩn tích hợp, API contracts, kiểm thử, CI và review sản phẩm thực.
6. Dùng **WIP, throughput, work item age, cycle time và SLE** để nhìn dòng công việc qua ranh giới nhóm mà không nhầm số task Done với giá trị đã giao.
7. Nhận diện phản mẫu: **nhiều Product Owner cạnh tranh cho một sản phẩm**, các backlog rời rạc, nhóm theo tầng kỹ thuật, “Done” cục bộ, điểm chặn bị giấu và quá nhiều tầng phê duyệt.
8. Áp dụng một tình huống nền tảng học trực tuyến để xây **bản đồ sản phẩm–mục tiêu–nhóm–phụ thuộc–bằng chứng**, rồi thực hành ra quyết định khi nhu cầu hoặc cấu trúc tổ chức thay đổi.

## 1. Phân biệt sản phẩm, dự án, thành phần và nhóm

Trong công việc hàng ngày, các tên gọi dễ bị trộn: “dự án thanh toán”, “team backend”, “platform team”, “sản phẩm ứng dụng học viên”. Nhưng khi phối hợp nhiều nhóm, cần làm rõ **đối tượng tạo giá trị** khác với **cách tổ chức thực hiện công việc**.

### 1.1. Các khái niệm thường gặp

| Khái niệm | Câu hỏi chính | Ví dụ trong nền tảng học trực tuyến |
|---|---|---|
| **Sản phẩm (product)** | Mang lại giá trị gì, cho ai, có ranh giới và mục tiêu nào? | Trải nghiệm học viên khám phá, đăng ký và học khóa trực tuyến |
| **Dự án (project)** | Nỗ lực có phạm vi/thời hạn/ngân sách nào để tạo thay đổi? | Chương trình mở luồng ghi danh cho kỳ khai giảng tháng 9 |
| **Thành phần (component)** | Khối kỹ thuật nào thực hiện một phần chức năng? | Giao diện giỏ khóa học, API đăng ký, database đơn hàng |
| **Nền tảng (platform)** | Cung cấp năng lực/dịch vụ dùng lại cho ai? | Dịch vụ xác thực, pipeline triển khai, công cụ vận hành phục vụ nhiều nhóm |
| **Dịch vụ (service)** | Cung cấp năng lực hoặc mức dịch vụ nào và có đối tượng tiêu thụ nào? | Dịch vụ thanh toán, tra cứu khóa, cấp quyền học |
| **Nhóm (team)** | Những người nào cộng tác để tạo/duy trì giá trị? | Nhóm học viên, nhóm quản lý khóa, nhóm năng lực nền tảng |
| **Dòng giá trị (value stream)** | Từ nhu cầu đến kết quả, công việc đi qua những bước nào? | Từ chọn khóa tới được cấp quyền và vào bài đầu |

Một sản phẩm có thể bao gồm nhiều thành phần, dịch vụ hoặc repository. Một nhóm có thể xây một phần của sản phẩm hoặc cung cấp một dịch vụ nền tảng cho nhiều sản phẩm. Một dự án có thể thay đổi nhiều sản phẩm, và một sản phẩm có thể tiếp tục tồn tại sau khi dự án kết thúc.

**Không dùng tên database hoặc repo làm tiêu chí duy nhất để đếm số sản phẩm.** Việc có \`frontend\`, \`backend\`, \`payments\` trong ba repository không tự chứng minh chúng là ba sản phẩm độc lập. Ngược lại, cùng một monorepo có thể chứa nhiều sản phẩm phục vụ những nhóm khách hàng và vòng quyết định khác nhau.

### 1.2. Theo Scrum, sản phẩm có ranh giới rõ

Theo **The Scrum Guide (2020)**, sản phẩm là phương tiện cung cấp giá trị, có **ranh giới rõ**, **stakeholders được biết** và **người dùng hoặc khách hàng được xác định**. Nó có thể là dịch vụ, sản phẩm vật lý hoặc thứ trừu tượng hơn.

Điều này quan trọng vì nếu không biết sản phẩm nằm ở đâu, sẽ khó trả lời:

- Product Goal nào đang hướng dẫn công việc?
- Product Backlog nào minh bạch toàn bộ công việc cần cho sản phẩm?
- Product Owner nào chịu trách nhiệm tối đa hóa giá trị?
- Những thay đổi nào phải tích hợp vào cùng Increment và DoD?
- Review sản phẩm nào cho phép stakeholders kiểm tra tiến triển thực?

Không nên coi “có dùng Scrum” là điều kiện để xác định sản phẩm. Những câu hỏi này cũng hữu ích khi tổ chức chọn Kanban hoặc mô hình khác, nhưng **tên role/artifact chính thức** thuộc Scrum chỉ nên áp dụng đúng bối cảnh.

### 1.3. Ví dụ dễ nhầm: ba ứng dụng không nhất thiết là ba sản phẩm

Một đơn vị có:

1. Web cho học viên.
2. Ứng dụng di động cho học viên.
3. Công cụ nội bộ để biên tập khóa.

Có ít nhất hai cách nhìn hợp lý:

- **Cách nhìn một sản phẩm chính:** web/mobile là các kênh cung cấp trải nghiệm học cho cùng đối tượng, có Product Goal và backlog chung. Công cụ biên tập có thể là phần cần thiết của sản phẩm để tạo giá trị tới học viên.
- **Cách nhìn nhiều sản phẩm/dịch vụ:** công cụ biên tập có người dùng nội bộ, mục tiêu hiệu quả tác nghiệp, chủ sở hữu và vòng phát hành riêng; nó có thể được quản lý như một sản phẩm nội bộ có phụ thuộc với sản phẩm học viên.

Không có đáp án cố định chỉ từ tên ứng dụng. Quyết định cần dựa vào **ranh giới giá trị, người dùng, quyền ưu tiên, độ phụ thuộc và khả năng tạo ra kết quả độc lập**.

### 1.4. Những dấu hiệu thường cho thấy một sản phẩm chung

- Các nhóm hướng tới **cùng một tập người dùng/kết quả** mà một phần riêng lẻ không đem lại đủ giá trị.
- Thứ tự ưu tiên ở nhóm này liên tục quyết định giá trị của nhóm khác; cần một **đầu mối tối ưu sản phẩm**.
- Có một hành trình hoặc khả năng tích hợp cần được kiểm chứng như một **Increment có thể sử dụng**.
- Quyết định về dữ liệu, nghiệp vụ, quyền hoặc API phải nhất quán theo ranh giới sản phẩm.
- Stakeholders chủ yếu đánh giá **kết quả tổng thể**, không chỉ năng suất của từng thành phần.

Đây là tín hiệu đánh giá, **không phải bộ điều kiện bắt buộc phải đúng hết**. Một sản phẩm lớn vẫn có các vùng giá trị được triển khai độc lập, và một nền tảng dùng chung có thể là sản phẩm phục vụ các nhóm phát triển như khách hàng nội bộ.

## 2. Xác định ranh giới sản phẩm trước ranh giới nhóm

Khi không rõ ranh giới sản phẩm, các nhóm dễ tối ưu việc cục bộ: nhóm UI muốn giao nhanh màn hình; nhóm API muốn ổn định schema; nhóm vận hành muốn giảm số lần deploy; Product Owner muốn học viên vào bài sớm. Những mục tiêu không nhất thiết đối lập, nhưng cần **một trật tự quyết định** để không làm mất kết quả chung.

### 2.1. Sáu câu hỏi để nhận diện một ranh giới sản phẩm

1. **Ai là người dùng/khách hàng?** Học viên, giảng viên, nhân viên quản trị, đối tác hay nhóm phát triển khác?
2. **Giá trị nào được tạo ra?** Học viên vào bài, người biên tập xuất bản khóa, hay Developers triển khai phần mềm an toàn?
3. **Có kết quả nào phải kiểm chứng đầu-cuối không?** Việc đăng ký, thanh toán, cấp quyền, học tập có cần nối với nhau?
4. **Ai cần quyết định thứ tự ưu tiên trên toàn ranh giới?** Nếu có hai yêu cầu cạnh tranh, ai tối ưu giá trị tổng thể?
5. **Ai chịu trách nhiệm về chất lượng/vận hành?** Phân quyền, trạng thái, dữ liệu và hỗ trợ thuộc một hay nhiều phạm vi?
6. **Có thể đo kết quả và thích ứng tương đối độc lập không?** Hay mỗi thay đổi luôn đòi hỏi đồng bộ nhiều vùng?

### 2.2. Bản đồ giá trị trước bản đồ hệ thống

Ví dụ:

~~~mermaid
flowchart LR
    N["Nhu cầu học viên:<br/>chọn khóa và bắt đầu học"] --> A["Khám phá khóa"]
    A --> B["Đăng ký hoặc thanh toán"]
    B --> C["Xác nhận quyền truy cập"]
    C --> D["Mở bài đầu"]
    D --> E["Học và phản hồi"]
    E -. "Dữ liệu học tập và phản hồi" .-> N
~~~

Bản đồ này bắt đầu bằng **kết quả người dùng**, không bắt đầu bằng các hộp \`frontend\`, \`backend\`, \`database\`. Sau khi thấy luồng giá trị, đội mới hỏi:

- Thành phần nào hỗ trợ mỗi bước?
- Ranh giới trách nhiệm nào tạo ít chuyển giao?
- Phụ thuộc nào phải giải quyết để một lát cắt hoạt động?
- Có phần nào phục vụ nhiều sản phẩm và cần một hợp đồng dịch vụ riêng?

### 2.3. Khi nào nên coi là nhiều sản phẩm?

Một nhóm cung cấp **hệ thống biên tập nội dung khóa học** cho nhiều đơn vị có thể có:

- Người dùng nội bộ là người tạo/duyệt nội dung.
- Mục tiêu rút ngắn thời gian xuất bản và bảo đảm chất lượng học liệu.
- Vòng ưu tiên và phát hành có thể quản lý riêng.
- API công bố khóa để ứng dụng học viên sử dụng.

Đây **có thể** là một sản phẩm/dịch vụ độc lập, tùy mô hình vận hành. Nếu chọn như vậy, cần mô tả **hợp đồng giữa hai sản phẩm** (trạng thái xuất bản, lịch sử phiên bản, quyền truy cập và trách nhiệm sự cố) thay vì giả vờ chúng không phụ thuộc nhau.

### 2.4. Hai cách phân chia đều có chi phí

| Lựa chọn | Lợi thế có thể có | Rủi ro cần kiểm tra |
|---|---|---|
| **Một product boundary rộng** | Ưu tiên xuyên hành trình, thấy mục tiêu người dùng đầu-cuối, tránh tối ưu cục bộ | Product Owner/Backlog quá rộng, nhiều nhóm lệ thuộc, khó hiểu toàn phạm vi |
| **Nhiều product boundaries rõ** | Có owner, người dùng và nhịp quyết định theo vùng giá trị; đội tự chủ hơn | Hợp đồng giữa sản phẩm và độ trễ phối hợp tăng; mục tiêu tổng thể có thể bị chia cắt |
| **Một platform product dùng chung** | Nhiều đội dùng năng lực chuẩn, giảm lặp công cụ, tăng an toàn | Platform trở thành hàng chờ tập trung nếu không có cách phục vụ và ưu tiên rõ |

**Ranh giới sản phẩm không nên bị vẽ theo sơ đồ tổ chức có sẵn một cách máy móc.** Đồng thời, không nên ép mọi thứ thành một Product Backlog khổng lồ khi các sản phẩm có người dùng và mục tiêu đủ độc lập.

### 2.5. Dấu hiệu cần xem lại ranh giới sản phẩm

- Product Owner liên tục không thể đưa ra một thứ tự backlog có ý nghĩa do hai nhóm khách hàng có nhu cầu hoàn toàn khác.
- Một sản phẩm phụ phải chờ backlog chung quá lâu dù có người dùng, outcome và vòng phản hồi riêng.
- Các phần được gọi là “sản phẩm độc lập” luôn phải release cùng nhau để người dùng thực hiện một tác vụ cốt lõi.
- Ranh giới ưu tiên không khớp ranh giới chất lượng, an toàn hoặc dữ liệu.
- Phối hợp liên sản phẩm tiêu tốn phần lớn cycle time, nhưng không có service contract rõ.

Đây là tín hiệu **kiểm tra và điều chỉnh**, không phải yêu cầu tái tổ chức mỗi khi có một sự cố.

## 3. Mục tiêu chung: hướng tới outcome thay vì tổng hợp các task Done

Sau khi nhận diện một product boundary, cần một **mục tiêu chung đủ rõ** để các nhóm biết lựa chọn ưu tiên, thiết kế và đánh đổi nào giúp người dùng.

### 3.1. Mục tiêu sản phẩm không phải danh sách chức năng

| Câu nói | Loại | Giới hạn |
|---|---|---|
| “Làm 20 API thanh toán” | Output kỹ thuật | Không nói người học đã đăng ký được chưa |
| “Hoàn thành giao diện ghi danh” | Output nhóm UI | Chưa nói API/DB/quyền đã tích hợp |
| “Đưa ra ba bản phát hành” | Hoạt động/giao hàng | Không tự chứng minh giá trị |
| “Học viên đủ điều kiện tự đăng ký và vào bài đầu an toàn, rõ ràng” | Kết quả/khả năng người dùng | Cần metric, guardrails và phạm vi để kiểm chứng |
| “Giảm tỷ lệ yêu cầu hỗ trợ vì không rõ trạng thái sau giao dịch” | Outcome có thể theo dõi | Cần mẫu số, phân loại và phương pháp đo đáng tin |

Mục tiêu chung không phải chỉ là một khẩu hiệu. Nó cần kết nối **đối tượng người dùng, kết quả, thời hạn/horizon thích hợp, điều kiện chất lượng và bằng chứng**, đồng thời không đóng cứng mọi giải pháp từ đầu.

### 3.2. Product Goal trong Scrum

Theo Scrum Guide 2020:

- **Product Goal** mô tả trạng thái tương lai của sản phẩm, là mục tiêu dài hạn để Scrum Team lập kế hoạch hướng tới.
- Product Goal là **commitment của Product Backlog**.
- Scrum Team phải hoàn thành hoặc từ bỏ một Product Goal trước khi nhận Product Goal tiếp theo; điều này không cấm làm rõ lộ trình hoặc thử nghiệm nhỏ liên quan trong quá trình thực hiện.
- Product Backlog là danh sách **emergent, ordered** những gì cần để cải thiện sản phẩm.

Ví dụ Product Goal cho sản phẩm học viên:

> **“Tạo hành trình đăng ký khóa và bắt đầu học tự phục vụ, để học viên đủ điều kiện có thể hoàn tất từ lựa chọn khóa tới bài học đầu mà không cần can thiệp thủ công trong các trường hợp chuẩn.”**

Mục tiêu này vẫn cần được làm rõ bằng **điều kiện chất lượng và chỉ số phù hợp**. Không lấy tỷ lệ chuyển đổi làm lý do bỏ phân quyền hoặc giảm tính đúng đắn thanh toán.

### 3.3. Mục tiêu chung khác Sprint Goal của từng nhóm

Khi nhiều Scrum Team cùng làm một sản phẩm:

- Họ cần cùng hướng tới **Product Goal** của sản phẩm.
- Các đội có thể có **Sprint Goal riêng của từng Scrum Team**, gắn với Sprint Backlog và cách đội đóng góp cho Product Goal.
- Một Sprint Goal không nên bị thay bằng danh sách task cố định; nó thể hiện **mục tiêu duy nhất của Sprint**, tạo sự tập trung và linh hoạt phạm vi.
- Không nên tự tuyên bố Scrum Guide bắt buộc **một Sprint Goal chung duy nhất cho tất cả các Scrum Team**. Việc phối hợp một mục tiêu liên đội hoặc nhịp Sprint đồng bộ có thể hữu ích theo bối cảnh, nhưng cần phân biệt với yêu cầu chính thức của khung.

Ví dụ:

| Phạm vi | Mục tiêu minh họa |
|---|---|
| **Product Goal chung** | Học viên tự đăng ký hợp lệ và vào bài đầu |
| **Sprint Goal nhóm trải nghiệm ghi danh** | Hoàn thiện một luồng đăng ký khóa miễn phí đầu-cuối đạt DoD cho nhóm thử |
| **Sprint Goal nhóm thanh toán** | Có khả năng xác nhận giao dịch và cập nhật quyền đúng trong một lát cắt tích hợp với nhóm liên quan |
| **Điều phối liên đội** | Hai Increment/đóng góp phải tích hợp tương thích để kết quả chung dùng được, không tạo Done ảo |

Nếu các đội thật sự cùng một Scrum product, cơ chế tích hợp và DoD chung phải đủ để những đóng góp không mâu thuẫn. Các Sprint Goals khác nhau **không cho phép mỗi nhóm bỏ qua mục tiêu và chất lượng chung**.

### 3.4. Dùng outcome có guardrails

Một bản mô tả mục tiêu chung có thể gồm:

~~~text
PRODUCT GOAL:
  Hoc vien hop le tu dang ky va vao duoc bai hoc dau tien.

DOI TUONG:
  Hoc vien dang ky khoa mien phi / khoa tra phi theo pham vi chon.

DAU HIEU GIA TRI:
  Ty le hoc vien du dieu kien vao bai dau,
  thoi gian tu ghi danh hop le den kha nang vao bai.

GUARDRAILS:
  Dung quyen, khong cap quyen thanh toan gia,
  bao ve du lieu va kha nang van hanh.

BAT DINH:
  Callback doi tac, tai cao diem, hanh vi nguoi dung moi.

QUYET DINH DUA TREN:
  Phan hoi nguoi hoc, su co, DoD, du lieu theo cohort,
  cac phu thuoc va nang luc thuc.
~~~

Đây là **mẫu hỗ trợ lập luận**, không phải artifact Scrum bắt buộc ngoài Product Goal. Nó giúp nhiều nhóm cùng hiểu **thành công là gì và điều gì không được đánh đổi**.

### 3.5. Mục tiêu chung không có nghĩa mọi nhóm làm cùng một việc

Một nhóm có thể xây luồng học viên, nhóm khác củng cố dữ liệu quyền, nhóm thứ ba làm nền tảng deploy. Những đóng góp khác nhau có thể cùng hướng tới một Product Goal nếu có **quan hệ nhân quả/hỗ trợ rõ**.

Vấn đề xuất hiện khi mỗi nhóm chỉ đặt mục tiêu riêng “hoàn thành 100% task” mà không ai kiểm tra **tác động lên sản phẩm**. Để tránh điều này:

1. Kết nối mỗi mục tiêu gần với **một kết quả sản phẩm hoặc năng lực cần tạo**.
2. Minh bạch phụ thuộc để thấy điều kiện đạt kết quả.
3. Cùng kiểm tra Increment tích hợp.
4. Khi học thêm từ người dùng hoặc chất lượng, **thay đổi thứ tự công việc có thẩm quyền**.

## 4. Scrum nhiều nhóm trên cùng một sản phẩm: những điều phải thống nhất

Một điểm dễ sai là mỗi đội “Scrum của riêng mình” với Product Owner, Product Backlog, DoD và lịch Review riêng, dù cùng tạo một sản phẩm duy nhất. Khi đó các đội có thể hoạt động tốt cục bộ nhưng không tạo được Increment tích hợp.

### 4.1. Điều Scrum Guide nói

Scrum Guide 2020 nêu khi Scrum Team trở nên quá lớn, nên cân nhắc tổ chức thành **nhiều Scrum Team gắn kết, mỗi đội tập trung vào cùng sản phẩm**. Khi đó họ cần chia sẻ:

1. **Cùng Product Goal.**
2. **Cùng Product Backlog.**
3. **Cùng Product Owner.**
4. **Cùng Definition of Done** do các Scrum Team thống nhất xác định và tuân thủ, trừ khi có chuẩn tổ chức cao hơn phải đáp ứng.

Các Scrum Team cùng sản phẩm cần tạo các **Increment tích hợp và có thể sử dụng**. Không nên diễn giải nhiều đội như nhiều dây chuyền giao từng mảnh không thể dùng, rồi chuyển trách nhiệm tích hợp cho một nhóm cuối.

### 4.2. Product Owner không phải một hội đồng chia đều quyền

Trong Scrum, **Product Owner là một người, không phải một ủy ban**, chịu trách nhiệm tối đa hóa giá trị sản phẩm và quản lý Product Backlog hiệu quả. Người này có thể **ủy quyền công việc** nhưng vẫn chịu trách nhiệm cuối về kết quả.

Ví dụ nhóm học viên có đại diện:

- Marketing đề xuất chiến dịch.
- Vận hành đề xuất công cụ hỗ trợ.
- Developers đề xuất thay đổi kỹ thuật.
- Bảo mật yêu cầu kiểm soát dữ liệu.
- Người phụ trách nội dung đề xuất quy tắc xuất bản.

Những bên này có thể tham gia làm rõ hoặc kiến nghị, nhưng nếu đây là **một Scrum product**, cần một Product Owner thực quyền để đưa ra thứ tự Product Backlog cho sản phẩm chung.

**Không nên nhầm “một Product Owner” với “một người tự làm mọi hoạt động yêu cầu”.** Người đó có thể phối hợp nhiều bên, có hỗ trợ phân tích sản phẩm và phân quyền tác nghiệp rõ; điều không được chia vụn là **accountability** về giá trị và Product Backlog của Scrum product.

### 4.3. Một Product Backlog không có nghĩa một danh sách phẳng hỗn loạn

Product Backlog chung có thể được tổ chức qua:

- Product Goal và các chủ đề outcome.
- Nhóm hành trình (khám phá, ghi danh, học tập).
- Sản phẩm con/khả năng/dịch vụ liên quan, nếu vẫn nằm trong product boundary.
- Liên kết phụ thuộc, rủi ro và nguồn bằng chứng.
- Các PBI được làm rõ dần, theo thứ tự ưu tiên.

Nhóm có thể dùng **views/filters** để xem PBI liên quan năng lực của họ. Nhưng những views không được trở thành các backlog cạnh tranh với **quyền sắp thứ tự riêng không thống nhất** khi cùng một Scrum product.

### 4.4. Definition of Done chung bảo vệ ý nghĩa “hoàn tất”

Nếu nhóm UI gọi Done khi giao diện được merge, nhóm backend gọi Done khi API unit tests pass và nhóm QA gọi Done khi test E2E chạy cuối tháng, **không có một chuẩn Increment chung**.

Một Definition of Done cho sản phẩm có thể đề cập theo chính sách tổ chức và chất lượng cần thiết:

- Thay đổi được tích hợp, build chung ổn định.
- Kiểm thử và các điều kiện chấp nhận áp dụng có bằng chứng.
- Quyền truy cập, dữ liệu và bảo mật phù hợp được bảo vệ.
- Giao diện/API và các consumer liên quan tương thích.
- Khả năng vận hành và phục hồi đủ cho phạm vi phát hành.
- Tài liệu/thông tin vận hành bắt buộc được cập nhật khi có tác động.

**DoD không cần là danh sách chung vô hạn cho mọi chi tiết**, nhưng phải tạo một mức chất lượng sản phẩm minh bạch. Một PBI chưa đáp ứng DoD không thuộc Increment Done; không hạ DoD chỉ vì Sprint sắp kết thúc.

### 4.5. Các nghi thức phối hợp không thay thế Scrum

Các nhóm có thể bổ sung đồng bộ liên đội, refinement xuyên nhóm, tích hợp chung hoặc kiểm tra dependency. Nhưng:

- **Scrum of Scrums không phải event bắt buộc** do Scrum Guide quy định.
- Không có quy định mọi Scrum Team cùng sản phẩm phải có **chung một Sprint Goal**.
- Không có quy định bắt buộc phải dùng một công cụ quản lý issue, story points hoặc một mô hình phân nhóm theo công nghệ.
- Một cuộc họp báo cáo liên đội không thay **Sprint Review** và kiểm tra Increment thật.

Thực hành phối hợp thêm vào cần phục vụ **phản hồi nhanh, giảm phụ thuộc và tích hợp**, không chỉ tăng lượng báo cáo.

## 5. Ranh giới nhóm: tối ưu dòng giá trị thay vì sơ đồ phòng ban

Sau khi xác định product boundary và mục tiêu, tổ chức cần chọn cách phân chia **con người và trách nhiệm** để tạo giá trị bền vững.

### 5.1. Team boundary là gì?

Ranh giới nhóm mô tả:

- **Khu vực giá trị hoặc trách nhiệm** nhóm chủ yếu phục vụ.
- **Năng lực** nhóm có để thực hiện công việc.
- **Quyền quyết định** được trao cho nhóm và giới hạn tổ chức.
- **Dịch vụ/đầu ra** nhóm cung cấp cho người dùng hoặc nhóm khác.
- **Giao diện phối hợp và phụ thuộc** mà nhóm cần quản lý.
- **Trách nhiệm chất lượng và vận hành** trước/sau khi phát hành.

Nó **không chỉ là ai quản lý nhân sự của ai** hoặc ai sở hữu một thư mục trong repository.

### 5.2. Cross-functional không có nghĩa mỗi người biết mọi thứ

Trong Scrum, Scrum Team là **cross-functional**: các thành viên **cùng nhau có đủ các kỹ năng cần thiết** để tạo giá trị mỗi Sprint. Điều này khác yêu cầu mọi Developer phải giỏi frontend, backend, database, test, UX, bảo mật và vận hành ở mức ngang nhau.

Nhóm có thể cần người chuyên sâu hoặc nhận hỗ trợ chuyên gia đúng lúc. Tuy nhiên, nếu **mọi PBI đều chờ một team khác làm phần cuối**, cần kiểm tra lại năng lực/ràng buộc vì sản phẩm khó có Increment thường xuyên.

### 5.3. So sánh ba cách phân chia phổ biến

| Phân chia | Ví dụ | Lợi thế có thể có | Rủi ro |
|---|---|---|---|
| **Theo tầng kỹ thuật** | Team UI, Team API, Team database, Team test | Tập trung chuyên môn, thống nhất công nghệ cục bộ | Mỗi user story qua nhiều hàng chờ và handoff; không ai sở hữu outcome end-to-end |
| **Theo luồng giá trị/hành trình** | Team ghi danh, Team học tập, Team biên tập | Có thể giao lát cắt dọc, quyết định gần người dùng hơn | Cần năng lực đa chức năng, giải quyết phần dùng chung và tránh phân mảnh trải nghiệm |
| **Theo nền tảng/dịch vụ chuyên biệt** | Identity, developer platform, payment integration | Chuyên môn sâu và năng lực dùng lại khi có nhu cầu thật | Thành điểm nghẽn nếu mọi thay đổi phải đặt ticket chờ; hợp đồng dịch vụ mơ hồ |

Không có cách chia **hoàn hảo cho mọi bối cảnh**. Nếu một phần yêu cầu kỹ thuật chuyên sâu hoặc kiểm soát tập trung có lý do thật, nhóm chuyên biệt có thể phù hợp. Điều cần làm rõ là **chi phí phụ thuộc** và cách để nhóm tạo sản phẩm không bị mắc kẹt.

### 5.4. Vertical slice giảm độ trễ bàn giao

Một lát cắt dọc có giá trị có thể gồm:

~~~text
Học viên ghi danh khóa miễn phí
  -> UI gửi yêu cầu
  -> API xác thực và kiểm tra điều kiện
  -> DB lưu ghi danh bền vững
  -> Quyền học được cấp đúng
  -> UI hiển thị trạng thái và đường vào bài
  -> Có test + bằng chứng DoD
~~~

Nếu phân theo tầng, bốn nhóm phải giao lần lượt UI → API → dữ liệu → QA. Nếu một nhóm có năng lực cross-functional và quyền làm việc xuyên các tầng trong ranh giới phù hợp, họ có thể hoàn tất **một hành vi người dùng nhỏ** với ít hàng chờ hơn.

**Không phải mỗi user story đều tách được một cách hoàn toàn độc lập.** Với thanh toán, cần xác thực bên ngoài và ràng buộc dữ liệu; nhóm có thể tạo lát cắt nhỏ hoặc spike giảm bất định nhưng không được gọi prototype chưa an toàn là Increment Done.

### 5.5. Team boundary và code ownership là hai lớp khác nhau

Một nhóm có thể chịu trách nhiệm chính với **năng lực ghi danh**, nhưng thay đổi của họ vẫn chạm:

- Frontend module của sản phẩm.
- Backend API.
- Schema dữ liệu.
- CI và test environment dùng chung.

Đây không phải lý do bắt buộc bốn nhóm khác nhau phải viết từng phần. Tổ chức có thể dùng **module ownership, code review, service contracts và kiểm soát thay đổi** để bảo vệ trách nhiệm kỹ thuật mà không tạo hàng chờ giao việc theo tầng.

Ngược lại, quyền sửa bất kỳ code nào không có review, test hoặc trách nhiệm cũng có rủi ro. **Autonomy phải đi cùng minh bạch và khả năng chịu trách nhiệm cho chất lượng.**

### 5.6. Cognitive load và tính bền vững của nhóm

Một nhóm được giao quá nhiều domain, công cụ và sự cố có thể không đủ khả năng tập trung. **Team cognitive load** là khái niệm hữu ích để xem nhóm phải nắm giữ bao nhiêu bối cảnh khi làm việc.

Nếu một nhóm ghi danh phải hiểu từ thanh toán, tìm kiếm, streaming video, analytics, SRE tới toàn bộ CI/CD, ranh giới có thể đã quá rộng. Cần cân nhắc:

- Năng lực nào có thể thành dịch vụ/nền tảng self-service?
- Chuyên môn nào cần hỗ trợ tạm thời để nhóm tự chủ về sau?
- Phụ thuộc nào đang tạo nhiều thay đổi ngữ cảnh?
- Có thể chia theo vùng giá trị đủ rõ mà vẫn giữ trải nghiệm tích hợp?

Không nên tối ưu “một nhóm sở hữu toàn bộ” bằng cách ép nhóm gánh mọi thứ. **Ranh giới tốt cân bằng khả năng giao end-to-end với chi phí nhận thức và phụ thuộc.**

### 5.7. Tham khảo Team Topologies nhưng không biến thành luật

Một cách phân loại thực hành quen thuộc từ **Team Topologies** gồm:

- **Stream-aligned team:** tập trung vào một luồng giá trị/người dùng đủ rõ.
- **Platform team:** cung cấp năng lực giúp các nhóm khác tự phục vụ, giảm gánh nặng lặp lại.
- **Enabling team:** hỗ trợ phát triển năng lực, tháo khó khăn kỹ thuật theo thời gian.
- **Complicated-subsystem team:** xử lý một vùng chuyên sâu khó đòi hỏi kiến thức đặc biệt.

Đây là **một mô hình tư duy về thiết kế đội**, không phải các vai trò hay cấu trúc bắt buộc của Scrum Guide. Một tổ chức nhỏ có thể không cần đủ bốn loại; một nhóm có thể chuyển cách tương tác khi nhu cầu thay đổi.

**Điểm quan trọng:** tên nhóm không phải kết quả. Nếu “platform team” chỉ tạo hàng chờ ticket và mọi đội phải chờ nhiều tuần, cần cải thiện hợp đồng, sản phẩm nội bộ hoặc tự động hóa, thay vì chỉ đổi tên thành “nền tảng”.

### 5.8. Sơ đồ chọn ranh giới nhóm từ luồng giá trị

~~~mermaid
flowchart TD
    P["Ranh giới sản phẩm + Product Goal"] --> V["Những hành trình / dòng giá trị chủ yếu"]
    V --> R["Năng lực, chất lượng và rủi ro cần có"]
    R --> T{"Nhóm có thể hoàn tất lát cắt end-to-end?"}
    T -->|"Có"| A["Thiết kế phạm vi ownership rõ và giữ khả năng tự quản"]
    T -->|"Chưa"| B["Tìm phụ thuộc, năng lực thiếu và cognitive load"]
    B --> C["Hỗ trợ chuyên môn / platform / điều chỉnh ranh giới"]
    C --> T
    A --> I["Tích hợp, kiểm chứng và phản hồi người dùng"]
    I --> F["Xem lại WIP, age, cycle time, chất lượng, outcome"]
    F -. "Dữ liệu mới" .-> P
~~~

Sơ đồ là công cụ hỏi, không phải lời hứa rằng chỉ cần đổi cấu trúc đội thì mọi phụ thuộc kỹ thuật sẽ biến mất.

## 6. Bản đồ phụ thuộc: không để những hàng chờ vô hình điều khiển sản phẩm

Ngay cả khi các nhóm được phân chia theo giá trị, phụ thuộc vẫn xuất hiện ở kiến trúc, dữ liệu, kỹ năng, phê duyệt và thời gian. Phối hợp hiệu quả không đòi hỏi **xóa mọi phụ thuộc**, mà đòi hỏi **thấy sớm, giảm khi có thể, quản lý phần còn lại minh bạch**.

### 6.1. Các loại phụ thuộc thường gặp

| Loại phụ thuộc | Ví dụ | Nguy cơ nếu không quản lý | Gợi ý xử lý |
|---|---|---|---|
| **API/hợp đồng kỹ thuật** | Nhóm ghi danh cần endpoint xác nhận trạng thái từ dịch vụ thanh toán | API đổi bất ngờ, giao diện và backend không khớp | Contract chung, consumer/provider checks, versioning |
| **Dữ liệu/schema** | Nhóm học tập cần biết quyền truy cập do nhóm ghi danh cấp | Trùng nguồn sự thật, ghi đè dữ liệu, truy cập trái quyền | Ownership dữ liệu, sự kiện/hợp đồng rõ, migration theo bước |
| **Môi trường/hạ tầng** | Nhiều nhóm chờ một staging environment | Hàng chờ tích hợp dồn cuối Sprint | CI, test environments, tự phục vụ, cô lập dữ liệu test |
| **Năng lực chuyên môn** | Cần chuyên gia bảo mật chung cho nhiều đội | Bảo mật bị kiểm tra muộn hoặc specialist quá tải | Tham gia từ refinement, phát triển năng lực đội, chính sách hỗ trợ |
| **Quyết định sản phẩm** | Marketing và vận hành tranh cùng năng lực ưu tiên | Các nhóm nhận chỉ đạo mâu thuẫn | Product Owner thực quyền hoặc cơ chế ưu tiên xuyên sản phẩm rõ |
| **Quy định/phê duyệt** | Điều kiện kiểm toán khi xử lý giao dịch | Trễ release hoặc bỏ kiểm soát bắt buộc | Làm rõ từ đầu, tạo bằng chứng liên tục, phân quyền phê duyệt |
| **Đối tác bên ngoài** | Nhà cung cấp thanh toán chưa cấp sandbox | Hứa Sprint Goal dựa trên điều kiện không kiểm soát | Spike sớm, phương án dự phòng, công khai rủi ro |
| **Thời gian phát hành** | Hai sản phẩm có lịch triển khai lệch | Version không tương thích, sự cố cho người dùng | Backward compatibility, rollout có kiểm soát, hợp đồng version |

Hãy phân biệt **phụ thuộc công việc** với **phụ thuộc quyền quyết định**. Một đội có thể triển khai kỹ thuật mà vẫn cần Product Owner lựa chọn thứ tự hoặc người có thẩm quyền phê duyệt rủi ro bảo mật. Phụ thuộc quyền hạn thường không được giải quyết chỉ bằng cách thêm API.

### 6.2. Ma trận phụ thuộc tối thiểu

| Bên cần | Bên cung cấp | Điều kiện cần | Trạng thái | Tác động nếu trễ | Phương án |
|---|---|---|---|---|---|
| Nhóm ghi danh | Dịch vụ thanh toán | Contract xác nhận hợp lệ và xử lý callback lặp | Chưa kiểm chứng | Không thể cấp quyền an toàn | Spike sandbox, mock có contract, test tích hợp |
| Nhóm học tập | Nhóm/quy trình quyền học | Nguồn sự thật về entitlement | Đã thống nhất schema v1 | Học viên không vào bài đầu | Consumer contract và test end-to-end |
| Nhóm phát hành | Platform/service vận hành | Pipeline, quan sát và quyền triển khai | Có một điểm chờ | Trễ Increment dùng được | Tự động hóa điều kiện thường gặp |
| Nhóm sản phẩm | Chuyên gia riêng tư | Quy định lưu dữ liệu cá nhân | Cần quyết định | Có thể vi phạm nghĩa vụ | Rà soát trước lựa chọn thiết kế |

Ma trận này không phải một lớp báo cáo bắt buộc. Đối với vài phụ thuộc nhỏ, lời ghi chú trong PBI và trao đổi trực tiếp có thể đủ. Với phụ thuộc xuyên nhóm kéo dài, **chủ sở hữu, điều kiện bàn giao và tác động** cần được thấy rõ để đội không lập kế hoạch dựa trên một cam kết không có thật.

### 6.3. Đồ thị phụ thuộc: vì sao “đợi tuần tới” cộng dồn

~~~mermaid
flowchart LR
    A["Lát cắt: học viên thanh toán và vào bài"] --> B["API xác nhận giao dịch"]
    A --> C["Quy tắc cấp quyền"]
    A --> D["Giao diện trạng thái"]
    B --> E["Sandbox đối tác"]
    C --> F["Dữ liệu quyền học"]
    D --> B
    F --> G["Kiểm thử tích hợp"]
    B --> G
    D --> G
    G --> H["Increment đáp ứng DoD"]
~~~

Nếu mỗi cạnh phụ thuộc biến thành một hàng chờ bàn giao, tổng lead time có thể lớn dù từng nhóm viết code nhanh. Cách cải thiện:

1. Làm rõ **hợp đồng và điều kiện** trước khi triển khai một phần phụ thuộc sâu.
2. Cho các nhóm liên quan **cộng tác trực tiếp ngắn hạn** để hoàn tất lát cắt thay vì chuyển ticket lòng vòng.
3. Đặt test contract và CI ở **ranh giới thành phần** để phát hiện mâu thuẫn sớm.
4. Tạo cơ chế tự phục vụ cho phụ thuộc lặp, ví dụ môi trường và test data.
5. Nếu phụ thuộc thường xuyên và kéo dài, **xem lại team boundary/architecture**, không chỉ tăng họp.

### 6.4. Đừng tối ưu từng hàng chờ mà bỏ luồng giá trị

Giả sử:

~~~text
UI:           2 ngày làm
API:          3 ngày làm
Dữ liệu:      1 ngày làm
Kiểm thử:     2 ngày làm

Chờ giữa các nhóm: 12 ngày lịch
~~~

Không thể cộng trực tiếp ngày làm với ngày lịch để tính một cycle time chính xác; cần cùng đơn vị và mốc thời gian. Nhưng ví dụ cho thấy **thời gian chờ** có thể lấn át **thời gian tạo thay đổi**. Tăng tốc riêng nhóm API từ ba xuống hai ngày có thể ít ảnh hưởng hơn giảm hàng chờ giữa các nhóm từ 12 xuống ba ngày.

Đây là lý do việc đánh giá phối hợp nên nhìn **toàn flow**, không chỉ utilization hay velocity từng team.

### 6.5. Các tương tác giữa nhóm nên có mục đích

Một cách tham khảo từ tư duy Team Topologies:

- **Collaboration:** nhiều nhóm cùng giải một vấn đề phức tạp trong thời gian giới hạn.
- **Facilitating:** nhóm có chuyên môn giúp nhóm khác hình thành năng lực và tự chủ hơn.
- **X-as-a-Service:** một nhóm cung cấp năng lực có giao diện và mức dịch vụ đủ rõ để nhóm khác sử dụng mà ít cần phối hợp.

Không cần áp mọi mô thức cho tất cả các cặp nhóm. Hãy hỏi: quan hệ hiện tại là **cùng phát minh giải pháp**, **giúp hình thành năng lực** hay **dùng một dịch vụ đã ổn định**? Nếu không phân biệt, tổ chức có thể đòi API self-service khi hợp đồng còn chưa hiểu, hoặc họp cộng tác hàng ngày cho một tác vụ đã có giao diện ổn định.

## 7. Một Product Backlog chung: cách ưu tiên khi nhiều nhóm cùng đóng góp

Khi nhiều Scrum Team cùng làm **một sản phẩm**, Product Backlog chung tạo minh bạch để tránh các đội tối ưu những kế hoạch riêng nhưng không hỗ trợ Product Goal.

### 7.1. Từ yêu cầu của nhiều bên đến một thứ tự có nghĩa

Ví dụ có năm đề xuất:

| Đề xuất | Bên quan tâm | Đóng góp tới Product Goal | Rủi ro/phụ thuộc |
|---|---|---|---|
| Xử lý callback thanh toán lặp | Vận hành, học viên | Bảo vệ cấp quyền và tính toàn vẹn | Cao, cần kiểm chứng đối tác |
| Hướng dẫn người học vào bài sau ghi danh | Học viên, hỗ trợ | Giảm bỏ dở sau đăng ký | Phụ thuộc trạng thái quyền đáng tin |
| Banner chiến dịch | Marketing | Có thể tăng lượng truy cập | Chưa giải quyết vấn đề thanh toán |
| Cải thiện CI cho luồng ghi danh | Developers | Giảm lỗi tích hợp, hỗ trợ Increment | Cần năng lực môi trường |
| Bộ lọc khóa học nâng cao | Người học | Có thể tăng khả năng tìm khóa | Cần dữ liệu nhu cầu, ưu tiên so với luồng ghi danh |

Product Owner cần cân nhắc **giá trị, rủi ro, chi phí chậm trễ, phụ thuộc, năng lực và thông tin mới**. Một PBI có tác động bảo mật hoặc tính đúng đắn quan trọng không nên bị xếp dưới vì “ít tạo giao diện”.

Không có một công thức ưu tiên duy nhất mà Scrum Guide bắt buộc. WSJF, RICE hoặc các thang điểm có thể hỗ trợ trao đổi nhưng phải hiểu giả định; không dùng số điểm để thay quyền quyết định và sự thật sản phẩm.

### 7.2. Nhiều đội không có nghĩa mọi PBI phải gắn cứng một đội ngay từ đầu

Nếu tất cả PBI được phân trước cho nhóm UI, API, DB, QA, backlog có nguy cơ trở thành **bảng kế hoạch theo tầng kỹ thuật**.

Một PBI tốt hơn nên mô tả **một khả năng/hành vi có giá trị**:

> **“Học viên đủ điều kiện ghi danh khóa miễn phí và vào bài đầu, với dữ liệu và quyền truy cập đúng.”**

Khi refinement và Sprint Planning, Developers có thể làm rõ kỹ năng cần thiết, phạm vi và ai sẽ phối hợp. Với mô hình nhiều nhóm, việc định hướng ownership vẫn hữu ích nhưng không nên khiến team boundary cản một lát cắt đầu-cuối.

### 7.3. Chia PBI theo hành vi, không chỉ theo công nghệ

**Chia theo tầng dễ gây hàng chờ:**

~~~text
ENR-01: Làm UI đăng ký
ENR-02: Làm API đăng ký
ENR-03: Làm bảng ghi danh
ENR-04: Viết test đầu-cuối
~~~

Những task này có thể cần để triển khai, nhưng **mỗi task riêng không nhất thiết tạo Increment có thể sử dụng**.

**Chia theo lát cắt dọc minh họa:**

| PBI | Hành vi người dùng | Điều kiện cốt lõi |
|---|---|---|
| **ENR-A** | Ghi danh khóa miễn phí hợp lệ và vào bài đầu | Danh tính, dữ liệu bền vững, đúng quyền, kiểm thử |
| **ENR-B** | Xem trạng thái đăng ký/thanh toán đáng tin | Không báo thành công giả, trạng thái lỗi rõ |
| **ENR-C** | Thanh toán qua một phương thức đã hỗ trợ và được cấp quyền đúng | Xác thực nguồn, callback lặp, idempotency |
| **ENR-D** | Tự giải quyết trường hợp thanh toán chờ phổ biến | Hướng dẫn và đường hỗ trợ đúng |
| **ENR-E** | Mở rộng phương thức thanh toán có bằng chứng nhu cầu | Hợp đồng, test tích hợp và ưu tiên |

Nếu sản phẩm thực tế chỉ có khóa trả phí, ENR-A không tự động là lát cắt có giá trị; đội nên chọn **khả năng tối thiểu có ý nghĩa** theo người dùng và ràng buộc thật.

### 7.4. Refinement xuyên nhóm để giảm bất định

Không cần kéo toàn bộ mọi nhóm vào mọi cuộc trao đổi. Nhưng khi một PBI ảnh hưởng nhiều ranh giới:

1. Product Owner giải thích mục tiêu và thứ tự.
2. Developers ở các vùng liên quan làm rõ **hành vi và phụ thuộc**.
3. Người có chuyên môn kiểm thử xác định ví dụ kiểm chứng.
4. Các bên xác nhận API/data contracts và điều kiện tích hợp.
5. Đội nhận diện phần nào chưa biết cần spike.
6. PBI được chia nhỏ để tăng khả năng hoàn tất **có chất lượng**.

Refinement là hoạt động liên tục trong Scrum; Scrum Guide không quy định một **sự kiện refinement chính thức** với timebox bắt buộc. Nhóm có thể tổ chức theo nhu cầu để giảm chờ và cải thiện chất lượng lập kế hoạch.

### 7.5. Một backlog chung vẫn cần khả năng nhìn workstream

Khi backlog có hàng trăm PBI, đội có thể dùng:

- Tags theo hành trình/outcome.
- Parent-child để quản lý mức khái quát và lát cắt.
- Dependency links để thấy thứ tự cần làm rõ.
- View cho từng nhóm/nhánh phát hành.
- Trạng thái validation/discovery.

Các view giúp quan sát nhưng **không thay Product Backlog có một thứ tự rõ**. Nếu mỗi nhóm tự có "Top 1" và mọi Top 1 đều mâu thuẫn, cần giải quyết ở quyền ưu tiên sản phẩm chứ không chỉ đồng bộ lịch họp.

## 8. Tích hợp liên tục và một tiêu chuẩn chất lượng chung

Ranh giới nhóm tốt vẫn có thể thất bại nếu tích hợp xảy ra quá muộn. Một Scrum product với nhiều đội cần kiểm tra **Increment tích hợp** liên tục, thay vì xem từng repository xanh là bằng chứng sản phẩm đã dùng được.

### 8.1. Ba mức “xong” cần phân biệt

| Mức | Mô tả | Có đủ kết luận sản phẩm đã có giá trị chưa? |
|---|---|---|
| **Task done** | Một phần code, test hoặc cấu hình được hoàn tất | Chưa; có thể chỉ là công việc nội bộ |
| **PBI/Increment đáp ứng DoD** | Phần sản phẩm liên quan đã tích hợp và đạt tiêu chuẩn chất lượng chung của Scrum product | Có thể được xem là Increment có thể sử dụng; vẫn cần xác nhận giá trị người dùng |
| **Phát hành và outcome** | Phần mềm được cung cấp an toàn tới phạm vi phù hợp, người dùng thực hiện tác vụ | Cần dữ liệu sử dụng/phản hồi; không đồng nghĩa tự động thành công |

Trong Scrum, **Increment phải đáp ứng DoD**. Nhiều Increment có thể được tạo trong một Sprint, có thể phát hành trước Sprint Review; Sprint Review **không phải gate phê duyệt release**.

### 8.2. “Merge code xong” chưa phải “Increment hoạt động”

Giả sử:

- Nhóm giao diện đã merge màn hình thanh toán.
- Nhóm API đã merge xử lý callback.
- Nhóm dữ liệu đã chạy migration.
- Nhóm test đang chờ môi trường.

Nếu người học không thể thực hiện thanh toán hợp lệ và mở bài đầu trong một môi trường đáp ứng điều kiện áp dụng, câu “bốn nhóm đều Done” là **báo cáo phần việc**, không phải bằng chứng Increment chung.

**Cách xử lý:** đặt tiêu chuẩn tích hợp, contract tests và kiểm tra hành trình quan trọng ngay trong luồng công việc; không đẩy tất cả verification sang một nhóm hoặc một Sprint cuối.

### 8.3. Các thực hành XP hữu ích cho phối hợp nhiều nhóm

**Extreme Programming (XP)** cung cấp những thực hành kỹ thuật có thể bổ sung cho Scrum/Kanban:

- **Continuous Integration:** tích hợp thay đổi nhỏ thường xuyên để phát hiện xung đột sớm.
- **Automated tests/TDD:** bảo vệ hành vi khi thay code và refactor.
- **Simple design và refactoring:** giữ ranh giới rõ, giảm phụ thuộc không cần thiết.
- **Collective code ownership và pair programming** khi phù hợp để giảm chờ chuyên gia/cá nhân.
- **Small releases:** tăng cơ hội nhận phản hồi từ phần mềm chạy thật.
- **Khách hàng tham gia thường xuyên:** tránh các nhóm triển khai theo những giả định nghiệp vụ khác nhau.

XP không tự bảo đảm các thay đổi schema, hợp đồng công khai hoặc dữ liệu tài chính an toàn. Những rủi ro đó vẫn cần kiểm chứng, khả năng khôi phục và thẩm quyền quyết định phù hợp.

### 8.4. Contract test và versioning ở ranh giới nhóm

Giả sử nhóm học tập gọi API GET /enrollments/{id} do nhóm ghi danh cung cấp. Hai bên cần thống nhất:

- Ý nghĩa từng trạng thái **PENDING, CONFIRMED, FAILED, EXPIRED**.
- Phân quyền người đọc, trường dữ liệu riêng tư.
- Khi nào entitlement được xem là hiệu lực.
- Hành vi khi API timeout hoặc trả dữ liệu cũ.
- Các trường nào bắt buộc, tùy chọn và cách thêm field không phá consumer.
- Kế hoạch thay version hoặc loại hành vi cũ.

Một **consumer-driven contract test** hoặc kiểm tra hợp đồng hai phía có thể phát hiện thay đổi phá vỡ sớm, nhưng vẫn cần integration/security tests khi liên quan dữ liệu và quyền thật.

### 8.5. Ví dụ hành vi chia sẻ giữa hai nhóm

~~~gherkin
Feature: Quyen truy cap bai hoc sau ghi danh

  Scenario: Chua xac nhan thanh toan khong cap quyen
    Given don D thuoc hoc vien A dang cho xac nhan thanh toan
    When A yeu cau mo bai hoc thuoc khoa cua don D
    Then dich vu hoc tap khong cho phep truy cap nhu da thanh toan
    And trang thai duoc trinh bay trung thuc

  Scenario: Giao dich hop le duoc xac nhan
    Given don D duoc xac nhan hop le theo nguon dang tin
    And quyen hoc duoc cap theo quy tac da thong nhat
    When A mo bai hoc dau cua khoa lien quan
    Then A co the truy cap theo quyen duoc cap

  Scenario: Tai khoan khac khong lay duoc quyen cua A
    Given quyen hoc thuoc hoc vien A
    And hoc vien B da dang nhap
    When B yeu cau du lieu quyen hoc cua A
    Then he thong tu choi theo chinh sach phan quyen
~~~

**Các kịch bản Gherkin là đặc tả bằng ví dụ, không phải bằng chứng test đã chạy.** Để tạo evidence cần triển khai kiểm thử, dữ liệu, build/môi trường và assertion thích hợp; những tình huống callback lặp/đồng thời còn cần kiểm tra dữ liệu và tính nguyên tử.

### 8.6. Kiểm chứng tích hợp theo nhịp công việc, không chờ cuối tháng

Một cách thực dụng:

1. Làm rõ hợp đồng và rủi ro trước khi nhiều nhóm cùng code.
2. Cho các thay đổi nhỏ đi qua CI phù hợp.
3. Sử dụng test fixtures và môi trường đại diện cho phần tích hợp.
4. Xác minh hành vi trên Increment chung khi PBI gần Done.
5. Thấy và xử lý broken build hoặc contract mismatch sớm.
6. Chỉ coi Increment Done theo chuẩn chung.
7. Nhận phản hồi user/stakeholder và vận hành để điều chỉnh Product Backlog.

Không cần biến mọi thay đổi thành một buổi phê duyệt liên đội. Mục tiêu là **giảm độ trễ khi phát hiện sai lệch** và không cần “Sprint tích hợp” như một trạng thái bình thường.

## 9. Kanban xuyên nhóm: đo dòng công việc tới giá trị, không chỉ hiệu suất từng cột

Khi một PBI đi qua nhiều nhóm, các dashboard cục bộ có thể cho thấy từng đội làm việc nhanh nhưng tổng **lead time** vẫn lớn. Kanban giúp trực quan hóa và cải tiến flow, nhưng phải định nghĩa **ranh giới dịch vụ và work item** phù hợp.

### 9.1. Một Definition of Workflow cho luồng tích hợp

Ví dụ một workflow minh họa:

~~~text
Ready
  -> Started / Implementation
  -> Cross-team Integration
  -> Verification
  -> Done (theo chinh sach chat luong)
~~~

Đối với luồng này cần ghi:

- Loại item được tính.
- Điểm bắt đầu/end và định nghĩa Done.
- Chính sách kéo việc, review, blocked và expedite.
- Cách **kiểm soát WIP** phù hợp năng lực thực.
- **Service Level Expectation (SLE)** với thời gian và xác suất.
- Ai xem dữ liệu và điều chỉnh workflow.

Nếu mỗi nhóm có Definition of Workflow riêng cho dịch vụ của mình, không nên tự cộng/suy diễn cycle time từng team thành **cycle time của sản phẩm**. Cần đo luồng xuyên các ranh giới theo timestamp chung khi muốn trả lời câu hỏi end-to-end.

### 9.2. Bốn flow metrics tối thiểu

| Chỉ số | Câu hỏi | Lưu ý khi phối hợp nhiều nhóm |
|---|---|---|
| **WIP** | Bao nhiêu item đã bắt đầu nhưng chưa Done? | Item chờ nhóm khác vẫn thuộc WIP trong boundary, không chuyển ra bảng ẩn |
| **Throughput** | Bao nhiêu item Done trong một kỳ? | Không đếm mỗi subtask của các nhóm như một PBI hoàn tất |
| **Work Item Age** | Item chưa Done đã ở workflow bao lâu? | Giúp phát hiện phụ thuộc lớn và việc bị kẹt giữa nhóm |
| **Cycle Time** | Item Done đi từ Started tới Done mất bao lâu? | Tính cả thời gian chờ trong boundary, cùng định nghĩa ở hai kỳ |

Khi dùng **SLE**, hãy công bố **thời lượng và xác suất**, loại item và dữ liệu/giả định hỗ trợ. Một SLA hợp đồng với đối tác và SLE nội bộ có thể khác nhau; không dùng SLE như lời hứa chắc chắn cho mỗi item.

### 9.3. Ví dụ nhìn toàn dòng thay vì nhìn từng nhóm

Giả sử một PBI có lịch sử minh họa (ngày lịch):

| Chặng | Thời gian |
|---|---:|
| Developers đang thực hiện và tích hợp | 3 ngày |
| Chờ môi trường liên đội | 6 ngày |
| Xử lý mismatch contract | 2 ngày |
| Chờ verification | 4 ngày |
| Xác minh đạt DoD | 1 ngày |
| **Tổng elapsed cycle time minh họa** | **16 ngày** |

Đây là ví dụ giả định với các chặng **không chồng nhau** và được đo cùng đơn vị. Nếu nhiều chặng diễn ra đồng thời, không thể chỉ cộng duration rồi coi đó là cycle time; phải lấy **timestamp Done − Started**.

Nếu chỉ báo “Developer làm ba ngày” thì mất **13 ngày liên quan chờ, xử lý phối hợp và hoàn tất**. Việc bổ sung năng lực môi trường/contract tests có thể mang lại nhiều giá trị hơn yêu cầu Developers viết code nhanh hơn một chút.

### 9.4. Bị chặn vẫn là WIP

Giả sử:

~~~text
Development: 3
Integration: 2
Blocked waiting provider: 2
Verification: 1
~~~

Nếu hai item blocked **không nằm trong Development/Integration/Verification**, tổng WIP là **8**. Nếu blocked là nhãn gắn trên hai item đã được tính trong Integration, WIP là **6**, không cộng hai lần.

Đừng chuyển các item chờ sang “On Hold” ngoài boundary chỉ để giảm WIP báo cáo, nếu chúng vẫn là công việc đã bắt đầu chưa Done. Làm vậy che phụ thuộc, khiến planning nhận thêm việc vượt khả năng hoàn tất.

### 9.5. Không dùng flow metrics làm bảng xếp hạng cá nhân

Nếu nhóm A xử lý bug nhỏ còn nhóm B xử lý tích hợp đối tác phức tạp, so throughput thô có thể vô nghĩa. Tương tự, một đội dành nhiều thời gian xử lý lỗi quyền và dữ liệu có thể có ít item Done nhưng đang bảo vệ giá trị cốt lõi.

Hãy kiểm tra:

- Cùng loại item và ranh giới Done chưa?
- Cùng cách chia PBI và work mix chưa?
- Có item blocked, canceled, reopen không?
- Dữ liệu chưa hoàn tất có bị loại khỏi kết luận không?
- Số liệu có đi cùng quality/outcome không?

Kanban giúp đội **tìm điểm nghẽn và cải thiện flow**, không được dùng làm lý do hạ DoD hoặc ép thành viên nhận thêm việc để tăng utilization.

## 10. Quyền quyết định và trách nhiệm: tránh “mọi người cùng phụ trách” nhưng không ai có quyền

Khi nhiều nhóm có cùng mục tiêu, tổ chức dễ nhầm **trách nhiệm chung đối với outcome** với **sự mơ hồ ai có quyền quyết định**. Mục tiêu chung cần **quyền quyết định rõ ở mỗi cấp**, không phải một hội đồng xét từng task.

### 10.1. Bản đồ quyền quyết định tối thiểu

| Quyết định | Trong một Scrum product, ai chịu trách nhiệm cốt lõi? | Ai cần tham gia/thông tin? |
|---|---|---|
| **Giá trị sản phẩm và thứ tự Product Backlog** | **Product Owner** | Stakeholders, Developers, chuyên gia liên quan |
| **Cách triển khai và kế hoạch Sprint Backlog** | **Developers của từng Scrum Team** | Product Owner, những đội phụ thuộc, hỗ trợ chuyên gia |
| **Hiệu quả Scrum và cải tiến áp dụng** | **Scrum Master** chịu trách nhiệm hiệu quả Scrum Team | Scrum Team và tổ chức |
| **Chất lượng Increment** | **Developers** xây đáp ứng DoD; các Scrum Team cùng product thống nhất tuân thủ DoD chung | Bảo mật, kiểm thử, vận hành và chuẩn tổ chức phù hợp |
| **Điều kiện bảo mật/pháp lý bắt buộc** | Vai trò có thẩm quyền theo tổ chức/quy định | Product Owner, Developers và chuyên gia liên quan |
| **Chính sách sử dụng nền tảng chung** | Người chịu trách nhiệm platform/service được tổ chức xác định | Những sản phẩm tiêu thụ dịch vụ và vận hành |
| **Phát hành tới một phạm vi người dùng** | Theo chính sách release/quản trị của tổ chức; Scrum không chỉ định một vai trò release duy nhất | Product Owner, Developers, vận hành, kiểm soát bắt buộc |

**Bảng là cách lập bản đồ thực tế**, không thêm các accountabilities mới vào Scrum Guide. Cần phân biệt ai **chịu trách nhiệm cuối** với ai **thực hiện, tham vấn hoặc hỗ trợ**.

### 10.2. Một Product Owner không thể có quyền trên giấy

Ví dụ Product Owner được ghi tên trong sơ đồ nhưng:

- Marketing có thể chỉ đạo nhóm UI nhận banner ngay.
- Vận hành có thể yêu cầu API dừng mọi công việc.
- Quản lý bộ phận phân phối nhân sự theo ưu tiên riêng.
- Một “ban điều hành backlog” họp hàng tuần để thay thứ tự mà Product Owner không có quyền chốt.

Tổ chức có thể có ràng buộc bắt buộc hoặc tình huống khẩn chính đáng. Nhưng nếu Product Owner **không có khả năng quản lý Product Backlog một cách hiệu quả**, việc tuyên bố đang dùng Scrum chung một sản phẩm là không thực chất.

Hướng cải thiện: xác định **loại quyết định nào có thể ủy quyền**, **điều kiện nào thuộc guardrails**, **thay đổi nào cần Product Owner xem lại** và **đường xử lý khi cấp tổ chức cần quyết định**.

### 10.3. Khi hai nhóm thuộc hai sản phẩm khác nhau

Không nên ép Product Owner của sản phẩm A tự quyết backlog sản phẩm B. Ví dụ sản phẩm **học viên** cần tăng năng lực xác thực từ dịch vụ **Identity Platform** dùng cho nhiều ứng dụng.

Hai sản phẩm có thể có:

- Product Goal và backlog riêng nếu chúng thật sự là hai products.
- Ưu tiên và người chịu trách nhiệm riêng.
- **Service agreement/contract**, chính sách yêu cầu thay đổi và đường xử lý sự cố.
- Kế hoạch phối hợp cho những thay đổi chung có tác động.

Khi tranh chấp năng lực platform, cần một cơ chế ra quyết định tổ chức hoặc hợp đồng dịch vụ rõ, không tự biến mọi yêu cầu của từng Product Owner thành “ưu tiên số một”.

### 10.4. Decision rights không có nghĩa họp phê duyệt mọi thứ

Các Developers cần tự quản kế hoạch và cách kỹ thuật phù hợp trong ranh giới đã xác định. Product Owner không phải duyệt từng tên class hoặc câu lệnh SQL. Ngược lại, Developers không nên tự đổi ưu tiên kinh doanh hoặc bỏ kiểm soát bắt buộc chỉ để code thuận tiện.

Một cơ chế hữu ích thường gồm:

1. **Quyết định cục bộ:** đội tự giải trong quyền kỹ thuật và DoD.
2. **Quyết định về thứ tự/giá trị:** Product Owner.
3. **Quyết định xuyên sản phẩm/dịch vụ:** owners/thẩm quyền của các ranh giới liên quan.
4. **Quyết định pháp lý, bảo mật, ngân sách:** người được tổ chức giao thẩm quyền.
5. **Rủi ro vượt quyền:** nêu dữ liệu và phương án để escalation, không che thông tin.

Điều này giúp nhiều nhóm **tự chủ nơi có thể, phối hợp nơi cần**, thay vì tập trung toàn bộ quyết định lên một người.

## 11. Nhịp phối hợp đủ nhẹ: trao đổi về mục tiêu và trở ngại, không chỉ lịch họp

Phối hợp nhiều nhóm thường tạo cám dỗ thêm cuộc họp: daily liên đội, weekly liên đội, risk meeting, dependency review, status review. Một số có ích; nhưng số lượng cuộc họp không phải thước đo mức độ Agile.

### 11.1. Mỗi hoạt động phải có một câu hỏi quyết định

| Hoạt động có thể chọn | Câu hỏi chính | Khi nào có ích? |
|---|---|---|
| **Refinement xuyên nhóm** | PBI ảnh hưởng ranh giới nào, cần AC/contract/spike gì? | Khi có phụ thuộc hoặc bất định nghiệp vụ/kỹ thuật |
| **Đồng bộ luồng ngắn** | Item nào đang bị chặn, ai giúp nó Done, quyết định nào cần ngay? | Khi các nhóm cùng giao lát cắt hoặc share workflow |
| **Kiểm tra Increment tích hợp** | Phần mềm có hoạt động đầu-cuối, đạt DoD không? | Thường xuyên, không đợi cuối dự án |
| **Sprint Review** (Scrum) | Stakeholders học được gì từ Increment và bối cảnh sản phẩm? | Là event Scrum, cần giữ đúng mục đích |
| **Retrospective** (Scrum) | Quy trình và chất lượng cần cải tiến thế nào? | Là event Scrum, chọn cải tiến có tác dụng |
| **Service/operations review** | Năng lực, sự cố, SLE, WIP và phụ thuộc dịch vụ thay đổi thế nào? | Khi vận hành có nhiều luồng hoặc services |
| **Product discovery** | Người dùng có cần giải pháp được ưu tiên không? | Khi giả thuyết còn chưa xác nhận |
| **Architecture/contract discussion** | Thay đổi này ảnh hưởng nhiều consumer hoặc rủi ro dữ liệu thế nào? | Khi quyết định khó đảo ngược hoặc ảnh hưởng nhiều nhóm |

Không phải mọi hàng tương ứng một cuộc họp mới. Đội có thể **gộp thông tin hoặc dùng đồng bộ không cùng thời điểm**, miễn là chức năng ra quyết định và phản hồi không biến mất.

### 11.2. Một sync liên đội không nên là báo cáo cá nhân

**Cách kém hiệu quả:**

> “Nhóm UI xong 7/10 task, nhóm API xong 4/8, nhóm QA chờ 3 ticket.”

**Cách hữu ích hơn:**

> “Mục tiêu cho học viên vào bài đang bị chặn bởi contract quyền; item ENR-C đã 12 ngày trong WIP. Hôm nay hai Developers từ các vùng liên quan xác minh sự kiện và cập nhật test contract. Nếu không giải quyết trước mốc kiểm chứng, Product Owner cần xem lại phạm vi phát hành; DoD và phân quyền vẫn giữ.”

Thông tin thứ hai tạo **hành động, người phụ trách và điều kiện kiểm tra**, không chỉ trạng thái.

### 11.3. Scrum events vẫn thuộc Scrum Team

Nếu sử dụng Scrum, không nên thay Daily Scrum của Developers bằng một cuộc status meeting đa cấp do quản lý chủ trì. Daily Scrum nhằm kiểm tra tiến triển tới Sprint Goal và điều chỉnh Sprint Backlog.

Một nhóm có thể dùng thông tin từ Daily Scrum để đưa ra vấn đề cần phối hợp liên đội. **Sự kiện phối hợp bổ sung** không phải lý do bỏ Scrum events nếu vẫn tự nhận Scrum nguyên vẹn.

### 11.4. Sprint Review của sản phẩm chung

Khi nhiều Scrum Team cùng một sản phẩm, stakeholders cần xem **Increment tích hợp và tiến triển tới Product Goal**, không chỉ bốn màn demo code từ bốn đội.

Việc phối hợp một review chung hoặc định dạng giúp mọi bên kiểm tra sản phẩm tổng thể có thể hữu ích. Nhưng không có nghĩa tất cả các nhóm phải đưa từng thành viên vào một buổi họp khổng lồ không có tương tác. **Tính minh bạch của Increment và khả năng điều chỉnh Product Backlog quan trọng hơn hình thức sân khấu**.

### 11.5. Đồng bộ có thể theo sự kiện thay vì theo lịch

Nếu hai nhóm chỉ có một phụ thuộc API quan trọng trong Sprint, có thể hẹn:

- Khi chuẩn bị contract.
- Khi provider thay schema.
- Khi contract test fail.
- Khi Increment tích hợp cần review.

Không cần mặc định họp liên đội mỗi ngày nếu không có thông tin cần xử lý. Ngược lại, nếu nhiều item liên tục bị chặn, một nhịp trao đổi ngắn có thể **giảm tổng thời gian chờ**; quyết định nên dựa trên hiệu quả thực.

## 12. Platform team và năng lực dùng chung: tự chủ hơn, không thêm hàng chờ

Một nền tảng dùng chung có thể là **sản phẩm nội bộ** với người dùng chính là các nhóm xây sản phẩm khác. Khi thành công, nó giúp họ giảm công sức lặp lại, phát hành an toàn và giải quyết những nhu cầu chung nhanh hơn.

### 12.1. Người dùng nội bộ cũng có nhu cầu và outcome

Ví dụ nền tảng triển khai cung cấp:

- Template CI/CD đã được kiểm chứng.
- Khả năng tạo test environment có giới hạn và quyền phù hợp.
- Quản lý secret, logging và giám sát theo chính sách.
- Công cụ self-service deployment và rollback/roll-forward phù hợp.
- Cách tích hợp xác thực dùng chung có contract ổn định.

**Outcome của platform** không phải “đã tạo 12 pipeline”. Có thể là:

- Nhóm sản phẩm triển khai thay đổi có chất lượng với **ít thao tác thủ công và ít thời gian chờ** hơn.
- Số lỗi cấu hình nghiêm trọng giảm.
- Thời gian tạo môi trường phù hợp giảm.
- Developers có khả năng tự giải quyết những nhu cầu phổ biến trong giới hạn an toàn.

Những chỉ số này cần định nghĩa rõ, không biến thành KPI thưởng theo số ticket platform đóng.

### 12.2. Từ ticket queue sang self-service

**Mô hình bị tắc:**

~~~text
Feature team A --ticket--> Platform approval queue
Feature team B --ticket--> Platform approval queue
Feature team C --ticket--> Platform approval queue
                           |
                           v
                     Một chuyên gia xử lý
~~~

**Mô hình hướng giảm chờ:**

~~~text
Feature teams
    -> Năng lực platform self-service đã được kiểm soát
    -> API/tool/template và tài liệu rõ
    -> Monitoring và support/escalation khi cần

Platform team
    -> Cải tiến dịch vụ, chính sách an toàn, khả năng dùng lại
~~~

Self-service **không có nghĩa không còn kiểm soát**. Nó nghĩa là những trường hợp thường gặp có quy tắc và bằng chứng đủ rõ để tự phục vụ; ngoại lệ hoặc rủi ro lớn vẫn cần đúng thẩm quyền.

### 12.3. Đừng biến mọi phần dùng chung thành platform product

Một thư viện được hai team dùng không tự cần một platform team riêng. Trước khi tách, hỏi:

1. Có người dùng nội bộ và nhu cầu lặp, đủ ổn định không?
2. Chi phí duy trì một dịch vụ riêng có thấp hơn chi phí phối hợp hiện tại không?
3. Dịch vụ có thể có API/contract, chất lượng, version và support rõ không?
4. Năng lực nào cần tập trung do chuyên môn/rủi ro, năng lực nào có thể lan tỏa cho các nhóm?
5. Có người chịu trách nhiệm thứ tự ưu tiên và chất lượng dịch vụ không?

Nếu chỉ một vài thay đổi dùng chung trong tháng, cộng tác trực tiếp hoặc một thư viện có owner rõ có thể đủ. Không phải mọi tổ chức Agile đều cần lập một “Platform Department”.

### 12.4. Ownership dữ liệu và source of truth

Các nhóm dùng chung dữ liệu cần thống nhất:

- **Đối tượng nghiệp vụ nào** là nguồn sự thật: đơn, quyền học, trạng thái thanh toán, hồ sơ khóa.
- Ai được phép ghi/cập nhật và theo quy tắc gì.
- Consumer lấy dữ liệu qua API, event hay bảng đọc được cho phép.
- Hành vi khi dữ liệu trễ, sự kiện lặp hoặc hệ thống lỗi.
- Cách di trú và đổi contract mà không phá phiên bản đang dùng.
- Yêu cầu bảo vệ thông tin cá nhân, retention và audit.

Không nên tự cho mọi nhóm ghi trực tiếp vào cùng bảng nghiệp vụ chỉ vì “cùng một sản phẩm”. Một sản phẩm chung vẫn cần **ranh giới trách nhiệm dữ liệu rõ** để bảo vệ tính đúng đắn.

### 12.5. Tương thích và release độc lập là năng lực cần xây

Khi hai nhóm không thể phát hành độc lập vì mỗi lần đổi API đều phá consumer, một cách giảm phụ thuộc có thể gồm:

- Contract tests giữa provider và consumer.
- API versioning, backward-compatible changes.
- Migration theo kiểu **expand–migrate–contract** khi thích hợp.
- Feature flags hoặc rollout theo phạm vi có kiểm soát.
- Theo dõi lỗi và kế hoạch khôi phục.

**Không bắt buộc phải tách thành microservices** để có hợp đồng và tương thích. Một modular monolith cũng có thể bảo vệ ranh giới thành phần, tự động kiểm tra và tích hợp thường xuyên.

## 13. Tình huống xuyên suốt: tổ chức bốn nhóm cho nền tảng học trực tuyến

> **Tình huống và toàn bộ số liệu dưới đây được giả định để minh họa**, không phải thông tin sản phẩm hoặc hiệu quả thực tế của một tổ chức cụ thể. Những quyết định kỹ thuật và cấu trúc nhóm cần được điều chỉnh theo quy mô, rủi ro và nghĩa vụ thực.

Một công ty vận hành nền tảng học có web cho học viên, dịch vụ đăng ký/thanh toán, nội dung video, hệ thống quản lý khóa và một pipeline triển khai dùng chung. Công ty có khoảng 24 người làm sản phẩm/kỹ thuật và muốn cải thiện trải nghiệm **đăng ký khóa → được cấp quyền hợp lệ → vào bài đầu** trước kỳ khai giảng.

### 13.1. Trạng thái A: mỗi phòng có một backlog riêng

Cách tổ chức cũ:

| Nhóm | Backlog riêng ưu tiên | Tiêu chuẩn Done cục bộ | Vấn đề đối với người học |
|---|---|---|---|
| **Frontend** | Hoàn tất giao diện theo thiết kế, banner, trang đơn | Merge UI và pass unit tests | UI có thể hiển thị trạng thái chưa phản ánh API |
| **Backend** | API, tích hợp đối tác, logic dữ liệu | Merge endpoints | Quy tắc quyền/đơn chưa được xác minh đầu-cuối |
| **Data** | Schema, migration, báo cáo | Migration thành công trên môi trường riêng | Consumer gặp lỗi phiên bản hoặc dữ liệu không khớp |
| **QA/Release** | Chạy test theo lịch, chuẩn bị phát hành | Hoàn tất một vòng kiểm thử | Phát hiện lỗi cuối kỳ, chờ sửa giữa nhiều nhóm |

Sơ đồ hiện tại:

~~~mermaid
flowchart LR
    PO1["Yêu cầu UI"] --> FE["Team Frontend"]
    PO2["Yêu cầu API"] --> BE["Team Backend"]
    PO3["Yêu cầu dữ liệu"] --> DA["Team Data"]
    FE --> QA["Team QA/Release"]
    BE --> QA
    DA --> QA
    QA --> INC["Hành trình học viên mới được kiểm tra"]
~~~

Các đội bận rộn, nhưng mỗi PBI đi qua nhiều hàng chờ. Nếu một nhóm kết thúc sớm, phần giá trị của họ vẫn **chưa dùng được** cho tới khi các thành phần khác hoàn tất và đạt chuẩn chung. Việc đơn thuần thêm một cuộc họp Scrum of Scrums hằng ngày có thể giúp nhìn phụ thuộc nhưng **không tự sửa ranh giới năng lực và quyền ưu tiên**.

### 13.2. Bước đầu: nhận diện sản phẩm và người dùng

Các bên tổ chức một buổi làm rõ:

| Câu hỏi | Giả định sau thảo luận |
|---|---|
| Người dùng chính của sản phẩm học viên? | Học viên tìm khóa, đăng ký và học |
| Giá trị đầu-cuối cần kiểm chứng? | Học viên đủ điều kiện vào bài đầu theo đúng trạng thái ghi danh/quyền |
| Ranh giới nào cần ưu tiên chung? | Các hành vi phục vụ trải nghiệm học viên trong product boundary đã chọn |
| Bộ công cụ CI/CD dùng chung phục vụ ai? | Nhiều nhóm phát triển; có thể quản lý như dịch vụ/nền tảng nội bộ với nhu cầu riêng |
| Hệ thống biên tập nội dung có là sản phẩm riêng không? | Chưa đủ dữ kiện; xem người dùng, vòng ưu tiên và hợp đồng liên quan trước khi chốt |
| Ai quyết định thứ tự Product Backlog của sản phẩm học viên nếu dùng Scrum? | Một Product Owner thực quyền |

**Điểm quan trọng:** họ chưa vội tuyên bố toàn bộ ứng dụng, mọi dịch vụ và công cụ đều là một sản phẩm. Trước tiên họ chọn **ranh giới giá trị cần cải thiện và người có thẩm quyền**.

### 13.3. Product Goal và cách xác nhận giá trị

Product Goal:

> **“Học viên đủ điều kiện tự hoàn tất ghi danh theo luồng được hỗ trợ, nhận quyền truy cập đúng và vào bài đầu mà không cần can thiệp thủ công trong tình huống chuẩn.”**

Các tín hiệu minh họa:

| Loại tín hiệu | Ví dụ | Điều kiện cần làm rõ |
|---|---|---|
| **Outcome** | Tỷ lệ học viên hợp lệ vào bài đầu sau ghi danh | Cohort, mẫu số, cửa sổ thời gian và phân đoạn miễn phí/trả phí |
| **Chất lượng** | Số sự cố cấp quyền sai, lỗi thanh toán bị báo thành công giả | Mức nghiêm trọng, số người bị ảnh hưởng, khả năng phát hiện |
| **Flow** | Cycle time end-to-end của PBI đạt DoD, work item age | Một Definition of Workflow và cách tính nhất quán |
| **Reliability** | Độ trễ và tỷ lệ lỗi của luồng ghi danh | Mức tải/thiết bị/môi trường và SLI/SLO phù hợp |
| **Phản hồi định tính** | Học viên có hiểu bước tiếp theo sau PENDING không? | Đối tượng thử, điều kiện quan sát và phương pháp ghi nhận |

Nhóm không đặt mục tiêu đơn thuần “tăng throughput 40%” vì có thể đạt bằng cách chia thẻ nhỏ hoặc hạ DoD. Cũng không thể tối đa hóa conversion bằng cách **cấp quyền khi chưa có xác nhận hợp lệ**.

### 13.4. Trạng thái B: nhóm theo khả năng tạo giá trị, platform làm dịch vụ hỗ trợ

Một phương án tổ chức sau khi đánh giá năng lực và phụ thuộc:

| Nhóm | Phạm vi công việc chính | Năng lực và quyền cần có | Phụ thuộc cần quản lý |
|---|---|---|---|
| **Enrollment Experience** | Từ chọn khóa đến ghi danh/đăng ký được xác nhận | UI/API/data/test phù hợp, có thể tạo lát cắt dọc | Payment integration, identity, entitlement contract |
| **Learning Experience** | Từ entitlement tới vào bài và tiến trình học | UI/API/data/test phù hợp cho trải nghiệm học | Hợp đồng quyền học, nội dung, streaming |
| **Course Operations** | Tạo và xuất bản nội dung đúng trạng thái/metadata | Năng lực phát triển và vận hành luồng xuất bản | Công bố khóa, API catalog, dữ liệu học liệu |
| **Developer Platform/Enabling** | CI/CD, environment, observability và hỗ trợ năng lực dùng lại | Self-service, contract, chính sách hỗ trợ | Nhu cầu của ba nhóm và kiểm soát tổ chức |

Đây là **phương án minh họa**, không phải cấu trúc Scrum bắt buộc. Nhóm Course Operations có thể thuộc cùng Scrum product hoặc là sản phẩm nội bộ riêng tùy kết quả phân tích product boundary. Nếu Enrollment và Learning cùng một Scrum product, các Scrum Teams của chúng chia sẻ **Product Goal, Product Backlog, Product Owner và DoD**. Nếu Developer Platform được xem là sản phẩm riêng, nó có người dùng và mục tiêu dịch vụ riêng, đồng thời cần hợp đồng với sản phẩm học viên.

### 13.5. Bản đồ product–team–service

~~~mermaid
flowchart TD
    G["Product Goal:<br/>Học viên đăng ký và vào bài đầu"]
    G --> BL["Product Backlog chung của Scrum product"]
    BL --> EN["Scrum Team: Enrollment"]
    BL --> LE["Scrum Team: Learning"]
    EN --> IN["Increment tích hợp theo DoD chung"]
    LE --> IN
    OP["Course Operations:<br/>product boundary cần làm rõ"] -->|"Contract catalog"| IN
    PL["Developer Platform:<br/>năng lực dùng chung"] -->|"CI, environment, observability"| EN
    PL -->|"Tự phục vụ, hỗ trợ"| LE
    IN --> FB["Phản hồi học viên + chất lượng + outcome"]
    FB -. "Điều chỉnh ưu tiên" .-> BL
~~~

Sơ đồ không diễn đạt một người có thể tự “sở hữu” mọi quyết định dịch vụ dùng chung. Nó chỉ làm rõ **trục giá trị sản phẩm** và **quan hệ hỗ trợ** để các bên quản lý đúng loại phụ thuộc.

### 13.6. Quyết định một Product Backlog chung

Các đề xuất đầu tiên được đặt cạnh nhau:

| PBI / việc cần xử lý | Giá trị/rủi ro | Phần liên quan | Quyết định ưu tiên minh họa |
|---|---|---|---|
| **ENR-01:** ghi danh khóa miễn phí và vào bài đầu đúng quyền | Lát cắt end-to-end sớm | Enrollment, Learning | Đầu tiên nếu phù hợp người dùng thật |
| **ENR-02:** trạng thái thanh toán PENDING/FAILED đáng tin | Tránh hiểu nhầm/cấp quyền sai | Enrollment, Payment contract | Làm rõ và kiểm chứng sớm |
| **ENR-03:** callback hợp lệ cấp quyền một lần | Bảo vệ tính toàn vẹn và nghĩa vụ | Enrollment, Learning, provider | Không hoãn rủi ro cấp quyền |
| **PL-01:** chuẩn hóa test environment | Giảm hàng chờ tích hợp | Platform và product teams | Phối hợp khi có tác động trực tiếp |
| **LE-01:** thông báo hướng dẫn mở bài đầu | Giảm bỏ dở sau ghi danh | Learning, Enrollment | Chọn dựa vào phản hồi |
| **MKT-01:** banner khóa hot | Có thể tăng nhu cầu | Enrollment UI | Cân nhắc sau rủi ro cốt lõi |

Product Owner chịu trách nhiệm thứ tự chung của **Product Backlog** nếu các hạng mục thuộc cùng Scrum product. Đối với PL-01, có thể có **backlog dịch vụ platform riêng** nếu platform là sản phẩm độc lập; điều quan trọng là **phụ thuộc và thỏa thuận ưu tiên được làm rõ**, không buộc PO của sản phẩm học viên sở hữu mọi nhiệm vụ của mọi platform.

### 13.7. Hai Sprint Goals khác nhau nhưng không mâu thuẫn

Ví dụ một nhịp làm việc:

- Scrum Team Enrollment: **“Tạo lát cắt ghi danh và phản hồi trạng thái đúng cho nhóm học viên đủ điều kiện.”**
- Scrum Team Learning: **“Học viên đã có entitlement hợp lệ có thể vào bài đầu ổn định và được từ chối đúng khi không có quyền.”**

Hai mục tiêu tập trung ở vùng giá trị khác nhau, nhưng cùng hỗ trợ Product Goal. Các Developers cùng làm rõ **contract quyền học và test tích hợp** trước khi một nhóm gọi công việc của họ Done.

Không biến Sprint Goal thành cuộc thi “team nào nhiều story points hơn”. Nếu nhóm Learning phải dành công sức xử lý lỗ hổng entitlement mà Enrollment phát hiện, việc phối hợp có thể có giá trị cao hơn hoàn tất thêm một giao diện ít ưu tiên.

### 13.8. Một Definition of Done chung, không phải một buổi ký nghiệm thu cuối

Một DoD minh họa cho Scrum product học viên:

~~~text
DOD — Sản phẩm học viên:
  - Increment tích hợp với phiên bản chung và build kiểm tra được.
  - AC quan trọng có bằng chứng test/review trên build phù hợp.
  - Quyền truy cập và dữ liệu đúng theo chính sách áp dụng.
  - API/contract giữa các thành phần không phá consumer liên quan.
  - Các rủi ro lỗi, log, quan sát và vận hành được kiểm soát theo mức áp dụng.
  - Những yêu cầu bảo mật, accessibility và tuân thủ bắt buộc đã đáp ứng.
  - Tài liệu vận hành hoặc thông tin người dùng được cập nhật khi cần.
~~~

Đây là **ví dụ**, không phải DoD chuẩn cho mọi sản phẩm. Các điều kiện cụ thể phải được đội và tổ chức quyết định. Điểm không thể bỏ: **không hạ DoD để đẩy work item sang Done sớm**.

### 13.9. Một phụ thuộc dữ liệu được xử lý theo contract

Trước đây Learning đọc trực tiếp một bảng đơn hàng do Enrollment cập nhật và tự suy ra quyền học. Khi trạng thái mới PENDING xuất hiện, Learning nhầm PENDING với CONFIRMED.

Cách cải thiện:

1. Thống nhất **nguồn sự thật của entitlement** và quy tắc nghiệp vụ.
2. Xác định ai có quyền tạo/sửa entitlement.
3. Công bố API/event contract và lỗi/timeout/duplicate behavior.
4. Viết ví dụ kiểm chứng cả **trạng thái hợp lệ và không hợp lệ**.
5. Bổ sung contract/integration/security tests.
6. Nếu thay schema, làm theo bước tương thích, không phá consumer đang dùng.

Không cần mặc định xây một microservice mới. Cấu trúc mô-đun với ranh giới rõ có thể giải quyết vấn đề trong hệ thống hiện có.

### 13.10. Khi môi trường kiểm thử trở thành điểm nghẽn

Giả sử trước thay đổi:

- Developers có thể viết code một lát cắt trong ba ngày.
- Việc chờ môi trường tích hợp mất bảy ngày.
- Một mismatch quyền học được phát hiện muộn và phải sửa qua hai nhóm.

Đội không chỉ yêu cầu “mọi người tăng velocity” mà xác định:

- Có thể tạo môi trường tự phục vụ, test data riêng và CI tích hợp không?
- Những contract nào có thể kiểm tra từ lúc commit?
- Ai chịu trách nhiệm và quyền truy cập nào cần cho environment?
- Thay đổi platform có chi phí gì và sẽ giảm thời gian chờ tới đâu?

Một can thiệp platform có thể giúp nhiều Sprint và nhiều sản phẩm. Nhưng cần **dữ liệu trước–sau có cùng định nghĩa**, không tuyên bố cải thiện chỉ vì số giờ họp giảm.

### 13.11. Phản hồi từ học viên làm thay đổi Product Backlog

Sau khi phát hành giới hạn một lát cắt đã đạt DoD, nhóm thấy một số học viên vẫn không biết phải làm gì khi thanh toán đang chờ. Product Owner có bằng chứng và ưu tiên **trạng thái/thông điệp rõ** hơn một banner mới.

Developers ở Enrollment và Learning phối hợp xây hành vi đúng, test trạng thái và quan sát outcome. Các đội không tự kéo mọi yêu cầu vào Sprint mà cân nhắc với Sprint Goals và năng lực hiện tại.

**Đây là Agile phối hợp nhiều nhóm:** việc học từ người dùng có thể dẫn tới **một quyết định Product Backlog chung**, không phải bốn backlog cập nhật lệch nhau.

### 13.12. Một dashboard đúng góc nhìn

Đội theo dõi:

| Góc nhìn | Tín hiệu | Câu hỏi |
|---|---|---|
| **Product Goal** | Học viên hoàn tất ghi danh/vào bài đúng quyền, phản hồi thực | Người dùng có đạt giá trị chưa? |
| **Increment/DoD** | Những lát cắt đã tích hợp và đáp ứng chất lượng | Có phần mềm thực sự dùng được không? |
| **Flow end-to-end** | WIP, throughput PBI đủ điều kiện, age/cycle time từ started tới Done | Các item bị kẹt ở đâu và bao lâu? |
| **Phụ thuộc** | Thời gian chờ contract, môi trường và quyết định | Hệ thống phối hợp có cản giao giá trị không? |
| **Technical quality** | Contract tests, sự cố, rủi ro dữ liệu/quyền và độ ổn định CI | Có thể tiếp tục thay đổi an toàn không? |
| **Platform outcome** | Độ trễ tạo environment, số bước thủ công, chất lượng deploy | Platform có làm các product teams tự chủ hơn không? |

Chỉ số được dùng để **điều chỉnh hệ thống**, không để kết luận “team nào đóng nhiều ticket thì đáng thưởng hơn”.

## 14. Khi nào giữ nhóm ổn định, khi nào thay ranh giới?

Tái tổ chức liên tục có thể phá hiểu biết và niềm tin trong nhóm. Ngược lại, giữ ranh giới lỗi thời có thể duy trì nhiều hàng chờ. Quyết định cần có **vấn đề quan sát được và phương án đánh đổi**.

### 14.1. Những tín hiệu đáng xem lại

- Phần lớn PBI của sản phẩm cần **ba hoặc bốn nhóm kỹ thuật nối tiếp** mới đạt DoD.
- Work item age tăng vì các nhóm chờ lẫn nhau, dù utilization của từng nhóm cao.
- Product Owner không thể có thứ tự Product Backlog chung do ranh giới sản phẩm hoặc quyền hạn mơ hồ.
- Một nhóm phải hiểu quá nhiều domain không liên quan; chuyển ngữ cảnh gây lỗi và chậm.
- Một platform team nhận mọi yêu cầu qua ticket, service contract không rõ và rất ít self-service.
- Cùng một thay đổi nghiệp vụ luôn đòi sửa nhiều component do thiết kế phân mảnh.
- Các nhóm liên tục đổ lỗi cho nhau khi có sự cố, không ai điều phối xử lý đầu-cuối.

Không phải một tín hiệu đơn lẻ đủ để kết luận phải đổi tổ chức. Cần đối chiếu **dữ liệu flow, rủi ro, phản hồi đội và nghĩa vụ**.

### 14.2. Trước khi tách đội, thử giảm phụ thuộc không cần đổi người

Một số can thiệp ít xáo trộn:

1. Làm rõ Product Goal, Product Backlog và quyền ưu tiên.
2. Thống nhất DoD và dựng một CI path tích hợp.
3. Tạo contract tests ở API được dùng chung.
4. Chọn một lát cắt dọc, giao quyền cho một nhóm/cặp nhóm hoàn tất từ đầu đến cuối.
5. Giới hạn WIP và giúp item gần Done trước khi mở việc mới.
6. Tăng năng lực cross-functional qua pair programming, mentoring hoặc hỗ trợ chuyên gia tạm thời.
7. Tự động hóa môi trường/phê duyệt lặp được phép.

Nếu những thay đổi này giảm được phụ thuộc và cycle time, **không nhất thiết phải đổi sơ đồ tổ chức**.

### 14.3. Khi thay ranh giới là lựa chọn hợp lý

Có thể cần tổ chức lại khi:

- Một năng lực có **người dùng, ưu tiên, vòng phản hồi và trách nhiệm riêng** đủ rõ để thành sản phẩm/dịch vụ.
- Một nhóm đang quá tải bối cảnh nhiều domain khiến khó tạo Increment.
- Các phụ thuộc liên đội lặp lại theo một ranh giới có thể được gom thành stream-aligned team.
- Chuyên môn kỹ thuật khó có thể cung cấp như dịch vụ hoặc hỗ trợ năng lực có chủ đích.
- Quyền quyết định và năng lực đang chia nhỏ quá mức khiến mỗi PBI phải xin nhiều cấp.

Thay đổi này cần kế hoạch **chuyển tri thức, trách nhiệm hệ thống, dữ liệu, on-call, backlog và guardrails**, không chỉ đổi tên phòng ban.

### 14.4. Các chi phí cần tính khi tái tổ chức

| Chi phí/rủi ro | Cách giảm |
|---|---|
| Mất hiểu biết ngữ cảnh và quan hệ làm việc | Chuyển giao theo lát cắt, pair, tài liệu contract, thời kỳ hỗ trợ |
| Product Backlog không rõ khi tách/gộp | Xác định Product Goal, PO và product boundary trước |
| Quyền vận hành/sự cố bị bỏ trống | Bản đồ service ownership, on-call, escalation và dữ liệu |
| Hạ tầng/test có nhiều owners | Chuẩn hóa pipeline, self-service và giao diện hỗ trợ |
| Chuyển người liên tục gây gián đoạn | Giữ nhóm tương đối ổn định để học và cải tiến |
| KPI trước/sau không còn so được | Ghi thay đổi granularity, work mix, DoD và nguồn dữ liệu |

Một tái tổ chức tốt có thể **đầu tư nhiều công sức ban đầu** trước khi lợi ích xuất hiện. Không nên yêu cầu ngay Sprint sau throughput phải tăng để chứng minh thành công.

### 14.5. Khi Product Goal thay đổi

Một Product Goal có thể hoàn tất hoặc bị từ bỏ có chủ đích khi bằng chứng mới cho thấy mục tiêu không còn thích hợp. Đội có thể cần làm rõ:

- Có vẫn cùng **sản phẩm và người dùng** không?
- Product Backlog cần thay đổi thứ tự/phạm vi thế nào?
- Các team boundaries hiện tại còn hỗ trợ luồng giá trị mới không?
- Năng lực chuyên môn hay platform nào cần tăng?
- Những dữ liệu và nghĩa vụ chất lượng nào phải giữ?

**Không coi mọi thay đổi mục tiêu là lý do tái tổ chức.** Nếu sản phẩm vẫn cùng ranh giới và năng lực nhóm phù hợp, có thể chỉ điều chỉnh backlog và phối hợp.

## 15. Xử lý các tình huống xung đột điển hình

Một mô hình phối hợp chỉ có giá trị nếu nó giúp đội ra quyết định khi các bên **không cùng ưu tiên hoặc thiếu điều kiện hoàn tất**.

### 15.1. Hai nhóm cùng một sản phẩm nhận lệnh trái chiều

**Tình huống:** Marketing yêu cầu nhóm giao diện ưu tiên banner chiến dịch, trong khi Product Owner ưu tiên sửa callback thanh toán để tránh cấp quyền sai.

**Điểm cần làm rõ:**

- Đây có phải một Scrum product với một Product Owner chịu trách nhiệm Product Backlog không?
- Banner có giá trị/chi phí chậm trễ nào đã được chứng minh?
- Lỗi callback ảnh hưởng an toàn/tính đúng đắn hay nghĩa vụ nào?
- Sprint Goals và kế hoạch Developers hiện tại chịu tác động gì?

**Hướng xử lý:** đưa thông tin để Product Owner quyết định thứ tự trong Product Backlog, giữ guardrails chất lượng và nghĩa vụ. Nếu có yêu cầu cấp tổ chức vượt quyền PO, cần nêu quyết định và ảnh hưởng minh bạch, không giao thêm công việc ngầm vào Sprint.

### 15.2. Platform team trở thành nút thắt cho mọi bản phát hành

**Tình huống:** mỗi Product Team phải mở ticket và chờ platform tạo environment, gắn secret và bấm release.

**Phân tích:** đây có thể là vấn đề năng lực, quyền hạn, chính sách kiểm soát hoặc thiếu tự động hóa. Chỉ tăng nhân sự platform chưa chắc giải quyết.

**Hướng xử lý:** phân loại thao tác lặp an toàn để self-service, chuẩn hóa pipeline, quyền và evidence; giữ phê duyệt có căn cứ cho tình huống rủi ro cao; đo thời gian chờ, lỗi triển khai và khả năng khôi phục.

### 15.3. Nhóm học tập nói “API sai”, nhóm ghi danh nói “consumer sai”

**Tình huống:** sau một thay đổi trạng thái quyền, học viên không vào được bài. Mỗi nhóm có unit tests pass.

**Hướng xử lý:** xử lý ảnh hưởng người dùng trước, phân biệt nguyên nhân với trách nhiệm sửa, kiểm tra contract và log/timestamp, thiết kế một integration test tái hiện. Sau đó thống nhất owner của giao diện, quy trình versioning và điều kiện Done.

Không biến post-incident review thành phiên đổ lỗi. Mục tiêu là **giảm khả năng lặp lỗi hệ thống**.

### 15.4. Một nhóm có Sprint Goal nhưng phụ thuộc đối tác chưa xác nhận

**Tình huống:** Sprint Goal yêu cầu thanh toán qua nhà cung cấp B; sandbox của B chưa được cấp và hợp đồng webhook chưa rõ.

**Hướng xử lý:** làm rõ bất định từ refinement; thử spike/contract validation khi phù hợp; không cam kết giả rằng mọi phụ thuộc sẽ đến đúng hạn. Developers và Product Owner trao đổi phạm vi để Sprint Goal còn có nghĩa; nếu điều kiện thay đổi, cập nhật kế hoạch đúng cơ chế Scrum.

Nếu chỉ có prototype giả lập, **không gọi là Increment thanh toán production đã đạt DoD**.

### 15.5. Mỗi nhóm có Product Owner riêng dù cùng một Scrum product

**Tình huống:** nhóm Enrollment có PO-1, Learning có PO-2, Data có PO-3; mỗi PO ra thứ tự khác nhau cho các PBI thuộc cùng một sản phẩm học viên.

**Phân tích:** nếu đây thật sự là nhiều Scrum Teams cùng một sản phẩm theo Scrum Guide, cần **cùng Product Owner, Product Backlog, Product Goal**. Các đại diện domain có thể hỗ trợ phân tích và ủy quyền tác nghiệp, nhưng không có ba accountability Product Owner độc lập cạnh tranh cho cùng Scrum product.

**Hướng xử lý:** làm rõ product boundary. Nếu ba sản phẩm độc lập thật, cho mỗi sản phẩm quyền ưu tiên và hợp đồng tương ứng; nếu một product, thống nhất PO và backlog chung.

### 15.6. Đội tổng hợp không thể release vì một module dùng chung

**Tình huống:** học viên muốn thấy trang tiến trình, nhưng dịch vụ nội dung thay schema phá hợp đồng đọc của Learning.

**Hướng xử lý:** kiểm tra backward compatibility, consumer/provider tests, cách vận hành version và chiến lược rollout. Nếu phụ thuộc lặp lại, xem lại team/service boundary và mô hình tương tác. Không lấy việc hai nhóm dùng cùng một repo làm bảo đảm tương thích.

### 15.7. Sự cố nghiêm trọng xảy ra ngoài giờ của một nhóm

**Tình huống:** học viên bị cấp nhầm quyền sau giao dịch; lỗi đi qua Enrollment, Payment và Learning.

**Hướng xử lý:** theo chính sách incident của tổ chức, làm rõ người điều phối, owner kỹ thuật, mức ảnh hưởng, thông tin cho người dùng và đường khôi phục. Sau khi giảm ảnh hưởng, xem nguyên nhân contract/idempotency, kiểm thử và ranh giới dữ liệu.

Một Product Goal chung không tự thay thế **trách nhiệm vận hành và quyền quyết định trong sự cố**.

### 15.8. Cấu trúc nhóm thay đổi giữa lúc dùng metrics

**Tình huống:** tháng trước các task được đếm theo team UI/API; tháng sau PBI được tạo theo hành trình ghi danh. Throughput tăng nhưng loại work item đã khác.

**Hướng xử lý:** version metric, ghi thay đổi định nghĩa, tách data streams và so bằng những đơn vị tương đồng. Không dùng số ticket thô để tuyên bố tái tổ chức tăng năng suất 40%. Theo dõi outcome, DoD, work item age và thời gian từ yêu cầu tới giá trị.

### 15.9. Đội muốn đạt mục tiêu chung bằng cách bỏ kiểm thử

**Tình huống:** hai đội đều thiếu thời gian và đề xuất bỏ một bước security test để “không chặn nhau”.

**Hướng xử lý:** xác định có phải guardrail/chính sách bắt buộc không; cải thiện cách đưa kiểm chứng sớm vào CI, giới hạn phạm vi phát hành hoặc đổi kế hoạch. Không hạ DoD hoặc bỏ kiểm soát pháp lý để đẩy nhanh dashboard.

### 15.10. Có quá nhiều người tham gia một cuộc sync

**Tình huống:** 35 người họp một giờ mỗi ngày để đọc task status nhưng không giải quyết phụ thuộc.

**Hướng xử lý:** hỏi quyết định nào cần người nào, tách thông tin có thể đọc không đồng bộ, chỉ gọi người liên quan khi có contract/incident/blocker; xem cycle time và độ trễ quyết định sau thay đổi. **Ít họp hơn không tự là tốt** nếu công việc bị kẹt vì thiếu trao đổi; mục đích là trao đổi đúng nơi.

## 16. Mười tám phản mẫu khi xác định sản phẩm, mục tiêu và ranh giới nhóm

### 16.1. “Một repository là một sản phẩm”

**Hệ quả:** chia sai product boundary, có thể tạo nhiều PO/backlog cho một hành trình người dùng.

**Cách sửa:** xác định người dùng, giá trị, mục tiêu, khả năng quyết định và Increment, không lấy số repo làm chuẩn.

### 16.2. “Một phòng ban là một Scrum Team”

**Hệ quả:** nhóm UI/API/QA trở thành hàng chờ cho nhau và không tạo Increment cross-functional.

**Cách sửa:** xem năng lực end-to-end, hỗ trợ kỹ năng, tự quản và team boundary theo giá trị.

### 16.3. “Một Product Goal chung = mọi đội có cùng task list”

**Hệ quả:** trộn mục tiêu dài hạn với kế hoạch chi tiết; mất khả năng thích ứng.

**Cách sửa:** Product Goal mô tả hướng giá trị; Scrum Teams có Sprint Goals/Sprint Backlogs phù hợp, cùng tạo tiến triển tới mục tiêu.

### 16.4. “Mỗi Scrum Team có một Product Owner riêng cho cùng một product”

**Hệ quả:** cạnh tranh ưu tiên, accountability bị chia vụn.

**Cách sửa:** nếu đúng một Scrum product, chia sẻ Product Owner/Product Backlog/Product Goal; cho phép người hỗ trợ phân tích trong quyền đã ủy quyền.

### 16.5. “Mỗi team giữ một DoD riêng rồi tích hợp sau”

**Hệ quả:** Done ảo, lỗi và làm lại phát hiện muộn.

**Cách sửa:** các Scrum Teams cùng product tuân thủ DoD chung và Increment tích hợp; các bước kỹ thuật cụ thể vẫn có thể khác theo rủi ro.

### 16.6. “Hoàn thành task là đã giao giá trị”

**Hệ quả:** dashboard task xanh nhưng học viên chưa đăng ký hoặc vào bài được.

**Cách sửa:** phân biệt task/PBI/Increment/release/outcome; kiểm chứng hành trình thực.

### 16.7. “Mọi phụ thuộc đều giải quyết bằng thêm cuộc họp”

**Hệ quả:** thời gian điều phối tăng nhưng hợp đồng, môi trường và quyền vẫn lỗi.

**Cách sửa:** xác định loại phụ thuộc, owner, contract, CI, self-service hoặc thay ranh giới khi cần.

### 16.8. “Bỏ hết cuộc họp liên đội mới là Agile”

**Hệ quả:** thiếu phản hồi/đồng bộ đúng lúc; nhiều nhóm phát triển giả định mâu thuẫn.

**Cách sửa:** giữ cơ chế ra quyết định, phối hợp ở điểm cần, có thể theo sự kiện và dùng dữ liệu.

### 16.9. “Mỗi nhóm tự tối ưu velocity là đủ”

**Hệ quả:** tối ưu cục bộ, tăng WIP và hàng chờ tích hợp.

**Cách sửa:** nhìn cycle time end-to-end, work item age, Increment và outcome; velocity không là thang so nhóm.

### 16.10. “Blocked không tính vì đã chuyển sang nhóm khác”

**Hệ quả:** WIP bị giấu, nhóm bắt đầu quá nhiều việc mới.

**Cách sửa:** tính theo Definition of Workflow và báo age của item chưa Done, không cất điểm nghẽn khỏi hệ thống.

### 16.11. “Platform team phải làm mọi việc dùng chung”

**Hệ quả:** điểm nghẽn tập trung, phát hành phải xin nhiều ticket.

**Cách sửa:** xây năng lực self-service, contract và hỗ trợ; tập trung chuyên môn thực sự cần thiết.

### 16.12. “Ai cũng sửa dữ liệu được vì đây là sản phẩm chung”

**Hệ quả:** source of truth không rõ, mất tính toàn vẹn và rủi ro phân quyền.

**Cách sửa:** xác định ownership nghiệp vụ, giao diện hợp đồng, quyền ghi và kiểm chứng.

### 16.13. “Có một buổi demo liên đội là đủ DoD”

**Hệ quả:** phần mềm trình diễn chạy nhưng chưa được tích hợp/kiểm thử và vận hành an toàn.

**Cách sửa:** DoD chung và bằng chứng thực; Review không thay tiêu chuẩn chất lượng.

### 16.14. “Tái tổ chức càng thường xuyên càng linh hoạt”

**Hệ quả:** mất kiến thức bối cảnh, kỹ năng hợp tác và quyền sở hữu.

**Cách sửa:** giữ nhóm tương đối ổn định, thay khi dữ liệu cho thấy chi phí ranh giới hiện tại cao.

### 16.15. “Không cần chủ sở hữu ưu tiên vì nhóm tự quản”

**Hệ quả:** các đội lấy việc theo người yêu cầu lớn tiếng nhất hoặc theo sở thích.

**Cách sửa:** phân biệt quyền ưu tiên giá trị với cách thực hiện kỹ thuật; tự quản cần mục tiêu và ranh giới rõ.

### 16.16. “Đã có API thì không cần hợp tác”

**Hệ quả:** hợp đồng sai ngữ nghĩa, trạng thái, bảo mật hoặc độ trễ; lỗi chỉ xuất hiện khi tích hợp.

**Cách sửa:** contract tests, versioning, trao đổi ngữ nghĩa khi có thay đổi và phản hồi sự cố.

### 16.17. “Một Scrum Master hoặc một PM phải quản lý mọi task của tất cả nhóm”

**Hệ quả:** biến Scrum thành lệnh–kiểm soát tập trung, giảm self-management và trách nhiệm Developers.

**Cách sửa:** Scrum Master hỗ trợ hiệu quả Scrum, Developers tự quản kế hoạch kỹ thuật, Product Owner quyết định Product Backlog; phối hợp thêm nếu phục vụ giá trị.

### 16.18. “Tổng throughput tăng là bằng chứng tổ chức tốt hơn”

**Hệ quả:** dễ bỏ qua đổi cách chia ticket, loại việc và điều kiện Done; có thể tăng output nhưng giảm quality.

**Cách sửa:** so cùng loại work item/DoD, báo WIP/age, chất lượng và outcome, tránh gán nguyên nhân từ một chỉ số.

## 17. Quy trình mười bước xác định sản phẩm chung và ranh giới nhóm

Đây là **quy trình gợi ý để triển khai tư duy**, không phải framework scaling Scrum bắt buộc hoặc chuỗi thủ tục phê duyệt mới.

### Bước 1 — Bắt đầu từ người dùng và dòng giá trị

Nêu hành trình hoặc vấn đề người dùng: “Học viên đủ điều kiện phải đăng ký và vào bài đầu theo quyền đúng.” Vẽ các bước chính từ nhu cầu tới kết quả, bao gồm bước chờ và phụ thuộc.

### Bước 2 — Xác định product boundary có căn cứ

Hỏi ai là người dùng, kết quả nào cần tối ưu chung, ranh giới quyết định ở đâu, những dịch vụ nào thực sự phục vụ một sản phẩm và phần nào có vòng giá trị riêng.

Không tự kết luận một sản phẩm = một ứng dụng, một repo hoặc một phòng ban.

### Bước 3 — Xác định một mục tiêu chung kiểm chứng được

Với Scrum product, làm rõ **Product Goal**. Kèm các dấu hiệu outcome/chất lượng và các guardrails, không chỉ số output hoặc danh sách tính năng.

### Bước 4 — Làm rõ accountability và quyền ưu tiên

Nếu nhiều Scrum Teams cùng product, bảo đảm **cùng Product Owner/Product Backlog/Product Goal và DoD**. Nếu nhiều sản phẩm, xác định chủ sở hữu/ưu tiên từng sản phẩm và hợp đồng giữa chúng.

### Bước 5 — Vẽ khả năng và phụ thuộc hiện tại

Xem các bước mà một PBI phải đi qua: kỹ năng, nhóm, API, dữ liệu, CI, phê duyệt, đối tác. Ghi **điểm chờ, ai phụ trách và điều kiện gỡ**.

### Bước 6 — Thiết kế team boundaries khả thi

Ưu tiên khả năng **giao lát cắt end-to-end** trong giới hạn cognitive load và năng lực thực. Quyết định có cần platform, chuyên gia hoặc enabling support dựa trên nhu cầu, không chạy theo tên cấu trúc.

### Bước 7 — Thống nhất contract và chất lượng tích hợp

Xác định **Definition of Done**, API/data contracts, security/quality requirements, test/CI path, môi trường và trách nhiệm sau release. Không để “Code Complete” của từng đội thay Increment đã tích hợp.

### Bước 8 — Chọn chính sách phối hợp ít đủ dùng

Chỉ thêm refinement/sync/review liên đội ở nơi có quyết định hoặc phụ thuộc cần xử lý. Phân biệt Scrum events chính thức với các thực hành bổ sung. Dùng thông tin bất đồng để hành động, không chỉ báo cáo trạng thái.

### Bước 9 — Quan sát flow, quality và outcome

Đo WIP, throughput, work item age, cycle time theo **cùng boundary**; kiểm tra DoD, sự cố và kết quả người dùng. Với platform, đo khả năng tự phục vụ và thời gian chờ của product teams.

### Bước 10 — Thử cải tiến và xem lại ranh giới

Chọn một vấn đề thật (ví dụ chờ môi trường hoặc contract mismatch), giả thuyết, phạm vi thử, guardrails và mốc xem lại. Nếu cách làm chưa tốt, sửa chính sách hoặc ranh giới **theo bằng chứng**, không tái tổ chức vì một biểu đồ đẹp hay một cuộc họp gây khó chịu.

### 17.1. Luồng quyết định tóm tắt

~~~mermaid
flowchart TD
    A["Người dùng + dòng giá trị"] --> B["Xác định product boundary"]
    B --> C{"Một sản phẩm hay nhiều sản phẩm?"}
    C -->|"Một Scrum product"| D["Product Goal / Backlog / PO / DoD chung"]
    C -->|"Nhiều products/services"| E["Goals/owners riêng + service contracts"]
    D --> F["Năng lực và ranh giới nhóm"]
    E --> F
    F --> G["Phụ thuộc + cơ chế tích hợp"]
    G --> H["Increment / service outcome có bằng chứng"]
    H --> I["Flow, quality, outcome và phản hồi"]
    I --> J{"Cơ chế và boundary còn phù hợp?"}
    J -->|"Có"| K["Giữ, cải tiến nhỏ"]
    J -->|"Chưa"| L["Điều chỉnh chính sách/contract/ranh giới"]
    K --> H
    L --> F
~~~

Điểm quan trọng của sơ đồ là **quyết định sản phẩm có trước quyết định phân nhóm**, sau đó phản hồi thực giúp điều chỉnh. Nó không ngụ ý mọi sản phẩm đều phải dùng Scrum.

## 18. Các mẫu sử dụng trực tiếp khi phối hợp nhiều nhóm

Những mẫu dưới đây giúp nhóm **thảo luận và ghi quyết định quan trọng**, không phải một bộ biểu mẫu bắt buộc của Scrum/Kanban/XP. Với nhóm nhỏ hoặc rủi ro thấp, có thể rút gọn.

### 18.1. Product Boundary Canvas

~~~text
TEN SAN PHAM / GIA THUYET BOUNDARY:
  [Ten de hieu, khong chi la ten repository]

NGUOI DUNG / KHACH HANG:
  [Nhom nguoi nao thuc su nhan gia tri?]

GIA TRI SAN PHAM:
  [Ket qua nguoi dung co the kiem chung]

RANH GIOI BAO GOM:
  [Cac hanh vi, dich vu/thanh phan can thiet]

RANH GIOI KHONG BAO GOM:
  [San pham/dich vu lien quan nhung co owner/vong gia tri rieng]

MUC TIEU CHUNG:
  [Product Goal neu dung Scrum; hoac outcome goal tuong ung]

BANG CHUNG THANH CONG:
  [Outcome, Increment DoD, quality/reliability]

GUARDRAILS:
  [Bao mat, du lieu, tuan thu, accessibility, van hanh]

NGUOI CHIU TRACH NHIEM UU TIEN:
  [Product Owner neu mot Scrum product; owner tuong ung neu khac]

PHU THUOC CHINH:
  [API/data, doi tac, platform, ky nang]

GIA DINH CHUA CHAC:
  [Nhung quyet dinh product boundary can kiem chung]

MOC XEM LAI:
  [Su kien/dieu kien va nguoi co tham quyen]
~~~

### 18.2. Team Charter theo luồng giá trị

~~~text
TEN NHOM:
  [Vi du: Enrollment Experience]

DONG GIA TRI / NGUOI DUNG:
  [Pham vi hoc vien/doi tac ma nhom phuc vu]

DONG GOP VAO PRODUCT GOAL:
  [Hanh vi / ket qua nhom giup tao]

NANG LUC NOI BO:
  [UI, API, test, data, operations... theo nhu cau thuc]

TRACH NHIEM CHINH:
  [Phan hanh trinh, component/service/data neu co]

KHONG THUOC PHAM VI:
  [Dieu gi thuoc nhom/san pham khac]

QUYEN QUYET DINH:
  [Ky thuat, planning, chuong trinh, incident theo pham vi]

PHU THUOC QUAN TRONG:
  [Ten owner, contract, chinh sach giai quyet]

CHUAN CHAT LUONG:
  [DoD chung neu cung Scrum product, policies lien quan]

KET QUA CO THE KIEM CHUNG:
  [Increment, thong so flow, quality/outcome]

CO CHE PHAN HOI:
  [Nguoi dung, Product Owner, service consumers]

RUI RO COGNITIVE LOAD:
  [Nhung domain/ky nang vuot kha nang hien tai]

TRIGGER XEM LAI BOUNDARY:
  [So hang cho, loai phu thuoc, su kien thay doi muc tieu]
~~~

Team Charter không được biến thành một hợp đồng cố định khiến Developers mất quyền tự quản. Nó phải làm rõ **điểm tiếp xúc và trách nhiệm**, đồng thời cho phép nhóm cải tiến cách thực hiện.

### 18.3. Dependency Agreement

~~~text
DEPENDENCY ID:
  [Vi du: DEP-ENR-LEARN-01]

BEN CAN:
  [Team/service/capability]

BEN CUNG CAP:
  [Team/service/owner]

HANH VI / CONTRACT:
  [API/event/data/decision cu the, hanh vi loi]

MUC TIEU ANH HUONG:
  [PBI, Product Goal, Increment, service outcome]

DIEU KIEN SAN SANG:
  [Dinh nghia thanh cong / kiem chung duoc]

CHINH SACH THAY DOI:
  [Versioning, thay contract, phan hoi khi thay]

RUI RO / DO TRE:
  [Blocked age, thoi gian cho, tai du lieu]

NGUOI PHU TRACH:
  [Owner / dau moi giai quyet, khong phai ten tap the mo ho]

PHUONG AN NEU KHONG SAN SANG:
  [Giam pham vi, spike, mock co contract, escalation]

MOC KIEM TRA:
  [Khi nao xac minh evidence va quyet dinh]
~~~

### 18.4. Bản ghi quyết định phối hợp

~~~text
QUYET DINH:
  [Vi du: Chon chung DoD cho Increment ghi danh + hoc tap]

BOI CANH / VAN DE:
  [Thoi gian cho, loi tich hop, user impact]

CAC PHUONG AN:
  A:
  B:
  C:

CO CHE CAN GIU:
  [Product Goal, quality, quyền uu tien, flow, feedback]

QUYET DINH VA LY DO:
  [Giai phap vua du theo du lieu hien co]

RUI RO / GIA DINH:
  [Phu thuoc, su co, cognitive load, ranh gioi]

AI CO QUYEN QUYET:
  [Product Owner / Developers / service owner / thẩm quyền]

BANG CHUNG THUC HIEN:
  [Test, Increment, user result, flow signal]

MOC XEM LAI:
  [Dieu kien / thoi diem]
~~~

### 18.5. Một status update hướng tới giá trị

**Không nên chỉ gửi:**

> “Team A 80% Done, Team B 60% Done, Team C 100% Done.”

**Mẫu hữu ích hơn:**

> **Mục tiêu sản phẩm:** Học viên đủ điều kiện tự ghi danh và vào bài đầu.
>
> **Increment có bằng chứng:** Luồng ghi danh miễn phí trên build đã đạt DoD; luồng thanh toán còn một vấn đề entitlement contract.
>
> **Điểm chặn:** ENR-C đang 9 ngày trong WIP, chờ xác nhận điều kiện callback và test tích hợp.
>
> **Quyết định cần thiết:** Product Owner xác nhận thứ tự khắc phục trước banner; nhóm kỹ thuật cùng điều chỉnh hợp đồng và test, chuyên gia bảo mật xác nhận yêu cầu quyền.
>
> **Điều không đánh đổi:** Không cấp quyền học trước xác nhận hợp lệ, không tính item chưa đạt DoD là Done.
>
> **Mốc xem lại:** Sau khi chạy kiểm chứng hợp đồng và rà soát rủi ro trên Increment tương ứng.

Mẫu báo cáo giúp lãnh đạo thấy **giá trị, rủi ro và quyết định cần hỗ trợ**, không nhầm tổng phần trăm task với tiến triển sản phẩm.

## 19. Workshop 90 phút: thiết kế lại bản đồ sản phẩm và nhóm

Workshop này được thiết kế để thực hành theo tình huống giả định, không phải Scrum event bắt buộc. Các bên tham gia có thể gồm Product Owner, Developers từ nhiều nhóm, Scrum Master/flow facilitator, người phụ trách platform, kiểm thử, vận hành và các chuyên gia có liên quan.

### 19.1. Đề bài

Tổ chức có bốn nhóm **Frontend, Backend, Database và QA**; mỗi nhóm dùng backlog riêng. Một user story “học viên thanh toán khóa và vào bài đầu” đi qua cả bốn nhóm. Phải sửa trạng thái sau callback trùng, nhưng **không ai có quyền ưu tiên xuyên nhóm**. Một môi trường tích hợp duy nhất tạo hàng chờ lớn.

Mục tiêu workshop:

1. Nêu product boundary và người dùng.
2. Viết một Product Goal/outcome tương ứng.
3. Đề xuất các team boundaries giảm handoff mà không quá tải kỹ năng.
4. Xác định trách nhiệm ưu tiên và DoD.
5. Vẽ một phụ thuộc có owner, điều kiện và cách kiểm chứng.
6. Chọn một cải tiến nhỏ và chỉ số đủ tin để xem tác dụng.

### 19.2. Kịch bản thời lượng

| Thời lượng | Hoạt động | Kết quả mong đợi |
|---|---|---|
| **0–10 phút** | Người học vẽ hành trình từ thanh toán tới bài đầu | Value stream và user outcome |
| **10–25 phút** | Thảo luận một product hay nhiều products/services | Product boundary + giả định |
| **25–40 phút** | Xác định Product Goal, người ưu tiên và DoD | Product decision rights |
| **40–55 phút** | Thiết kế team boundaries và năng lực end-to-end | Team map + điểm thiếu kỹ năng |
| **55–70 phút** | Chọn một PBI, vẽ dependency và contract | Dependency agreement |
| **70–80 phút** | Chọn WIP/age/cycle time, quality và outcome | Scorecard có định nghĩa |
| **80–90 phút** | Công bố quyết định và điều kiện xem lại | Một thử nghiệm cải tiến có owner |

### 19.3. Các thẻ thông tin bất ngờ

**Thẻ A — Có thêm một khách hàng nội bộ:** nhóm biên tập khóa muốn tự phát hành nội dung, có mục tiêu và nhịp riêng. Ranh giới sản phẩm nên thay đổi hay chỉ thêm một service contract?

**Thẻ B — Platform thiếu năng lực:** hai product teams cùng phải chờ chuyên gia CI/CD bảy ngày. Giải pháp là tách thêm team, bổ sung self-service hay tổ chức đào tạo?

**Thẻ C — Một Product Owner trên giấy:** Marketing và vận hành có thể giao task thẳng vào Sprint. Cần làm rõ quyền nào và phối hợp với ai?

**Thẻ D — Contract bị phá:** API trạng thái quyền thay đổi khiến ứng dụng di động bản cũ không vào bài được. Làm sao xử lý sự cố và tránh lặp?

**Thẻ E — Hai Sprint Goals xung đột:** một đội muốn ổn định entitlement, đội khác muốn phát hành UI mới phụ thuộc entitlement chưa đúng. Lựa chọn nào bảo vệ Product Goal và DoD?

**Thẻ F — Bảng metrics đẹp hơn sau tái tổ chức:** ticket Done tăng mạnh nhưng PBI được chia nhỏ hơn; đội sẽ báo cáo thế nào cho trung thực?

### 19.4. Rubric đánh giá workshop

| Tiêu chí | Chưa đạt | Đạt tối thiểu | Tốt |
|---|---|---|---|
| **Product boundary** | Chỉ liệt kê repo/phòng ban | Có người dùng, giá trị và ranh giới | Nêu cả phần độc lập và phụ thuộc với giả định |
| **Goal chung** | Danh sách task hoặc công nghệ | Một outcome có thể kiểm chứng | Outcome có quality guardrails và feedback |
| **Scrum accountability** | Nhiều PO tranh cùng backlog | PO/Backlog/DoD chung nếu cùng Scrum product | Phân quyền tác nghiệp rõ, không chia vụn accountability |
| **Team boundaries** | Theo chức năng, nhiều handoff | Có lát cắt end-to-end | Cân bằng cross-functional, cognitive load và service contracts |
| **Integration** | Mỗi team Done riêng | Có test và DoD chung | CI/contracts, kiểm chứng sớm, recovery và quyền rõ |
| **Flow và outcome** | Chỉ đếm task/velocity | Có WIP/age/cycle time và user outcome | Metric contract, guardrails và giải thích bất định |
| **Cải tiến** | Chỉ thêm họp hoặc đổi tên | Một thay đổi có owner | Có giả thuyết, bằng chứng, thời điểm xem lại |

Workshop đạt mục tiêu khi các bên có thể **giải thích vì sao đề xuất ranh giới giúp người dùng nhận giá trị sớm hơn**, không chỉ tạo sơ đồ tổ chức hấp dẫn.

## 20. Bài tập vận dụng

### Bài tập A — Một sản phẩm hay ba sản phẩm?

Một tổ chức có ba repository: ứng dụng web học viên, ứng dụng mobile học viên và backend đăng ký. Cả ba cùng phục vụ hành trình chọn khóa–ghi danh–học, có cùng người dùng và Product Goal.

**Yêu cầu:** Ba repository có tự tương ứng ba sản phẩm không? Hãy nêu ít nhất bốn câu hỏi để xác định product boundary.

<details>
<summary>Gợi ý đáp án</summary>

Không. Repository là ranh giới kỹ thuật, không tự là ranh giới sản phẩm. Cần hỏi ai nhận giá trị, outcome nào phải kiểm chứng đầu-cuối, Product Goal/ưu tiên có chung không, stakeholder nào đánh giá kết quả, việc release có cần tích hợp và chất lượng/dữ liệu được quản lý theo ranh giới nào. Với dữ kiện đã cho, có căn cứ mạnh để xem đây là **các thành phần/kênh của một sản phẩm học viên**, nhưng vẫn cần kiểm chứng trách nhiệm và bối cảnh tổ chức.

</details>

### Bài tập B — Product Owner của nhiều Scrum Teams

Ba Scrum Teams cùng tạo **một sản phẩm học viên**. Mỗi đội có Product Owner riêng, Product Backlog riêng và thứ tự ưu tiên mâu thuẫn.

**Yêu cầu:** Theo Scrum Guide 2020, những điều gì phải chung? Những đại diện domain có thể tiếp tục đóng góp bằng cách nào?

<details>
<summary>Gợi ý đáp án</summary>

Các Scrum Teams cùng một sản phẩm cần chia sẻ **Product Goal, Product Backlog, Product Owner** và **Definition of Done**. Product Owner là một người chịu trách nhiệm tối đa hóa giá trị và quản lý Product Backlog hiệu quả, không phải hội đồng ba người. Đại diện domain có thể tham gia refinement, phân tích, đề xuất thứ tự hoặc thực hiện tác vụ được ủy quyền, nhưng không biến accountability cuối thành ba người độc lập tranh nhau. Nếu thực tế là các sản phẩm độc lập, cần xác định lại product boundary và service contracts trước khi áp quy tắc cho cùng một Scrum product.

</details>

### Bài tập C — Product Goal và Sprint Goal

Hai Scrum Teams cùng làm sản phẩm học viên. Team A có Sprint Goal về ghi danh miễn phí; Team B có Sprint Goal về đọc entitlement và mở bài đầu.

**Yêu cầu:** Có bắt buộc cả hai dùng một Sprint Goal giống hệt không? Điều gì phải thống nhất để không phá Product Goal?

<details>
<summary>Gợi ý đáp án</summary>

Scrum Guide yêu cầu cùng Product Goal, Product Backlog, Product Owner và DoD khi các Scrum Teams cùng sản phẩm; không đặt quy tắc mọi Scrum Team phải có Sprint Goal giống hệt nhau. Mỗi Scrum Team có Sprint Goal giúp điều hướng Sprint Backlog của mình. Tuy nhiên các mục tiêu không nên dẫn tới Increment không tương thích: cần làm rõ hợp đồng quyền học, điều kiện tích hợp, DoD, sự phụ thuộc và cách cùng kiểm tra tiến triển tới Product Goal.

</details>

### Bài tập D — Tại sao bốn nhóm Done vẫn chưa có Increment?

Nhóm UI đã merge màn hình đăng ký, nhóm API đã hoàn thành endpoint, nhóm Data đã deploy schema và nhóm QA mới bắt đầu chuẩn bị E2E tests.

**Yêu cầu:** Điều gì có thể báo cáo là Done và điều gì chưa thể? Đề xuất cơ chế sửa.

<details>
<summary>Gợi ý đáp án</summary>

Có thể báo các **task kỹ thuật** đã xong theo điều kiện cục bộ, nhưng chưa thể gọi toàn bộ hành trình là **Increment đạt DoD** nếu chưa tích hợp, kiểm chứng quyền, dữ liệu và hành vi. Nên chọn PBI/lát cắt dọc, làm rõ DoD chung, chuẩn bị contract/API tests trước, tích hợp qua CI và test end-to-end ở điểm thích hợp, hạn chế chuyển việc sang hàng chờ cuối. Báo tiến triển với sự thật rằng phần giá trị chưa được kiểm chứng đủ.

</details>

### Bài tập E — Xác định team boundary

Một công ty có Team Frontend 6 người, Team Backend 6 người, Team QA 4 người. Hầu hết story đều phải chờ cả ba nhóm.

**Yêu cầu:** Phác thảo một cách tổ chức lại ít nhất hai nhóm theo luồng giá trị và nêu một rủi ro mới của phương án.

<details>
<summary>Gợi ý đáp án</summary>

Có thể tổ chức nhóm **Enrollment Experience** với UI/API/test cho hành trình ghi danh và nhóm **Learning Experience** với UI/API/test cho hành trình vào bài. Những năng lực dùng chung cần service contracts hoặc hỗ trợ chuyên môn, không mặc định lập thêm nhóm cho mọi thành phần. Rủi ro mới là thiếu năng lực chuyên sâu, cognitive load, hợp đồng dữ liệu giữa các nhóm và chuyển giao tri thức. Cần điều chỉnh theo sản phẩm thật, sự ổn định của nhóm, quyền vận hành và tác động dòng công việc; không chỉ di chuyển người trên sơ đồ.

</details>

### Bài tập F — Bản đồ phụ thuộc

Một PBI về thanh toán chờ: sandbox đối tác, contract entitlement, test dữ liệu lặp và quyết định về điều kiện cấp quyền.

**Yêu cầu:** Viết bốn dòng của dependency agreement, gồm người/bên cần, người/bên cung cấp, điều kiện kiểm chứng và hướng xử lý nếu chậm.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ:

| Bên cần | Bên cung cấp | Điều kiện kiểm chứng | Nếu chậm |
|---|---|---|---|
| Enrollment | Đối tác thanh toán | Sandbox và callback test cases | Spike/mock có contract, công khai rủi ro |
| Learning | Enrollment/entitlement owner | API/event trả trạng thái quyền đúng | Contract test, phối hợp trực tiếp |
| Developers | Người chịu trách nhiệm dữ liệu | Ràng buộc không tạo quyền trùng sai | Test DB/concurrency, làm rõ source of truth |
| Product teams | Product Owner/chuyên gia bắt buộc | Quy tắc cấp quyền được xác nhận | Làm rõ quyết định, cập nhật PBI/phạm vi |

Cần gắn owner thật, thời gian xem lại và tác động Product Goal khi dùng trong thực tế.

</details>

### Bài tập G — Tránh tối ưu cục bộ

Một PBI mất 3 ngày làm kỹ thuật, 8 ngày chờ môi trường và 2 ngày kiểm chứng trong mô hình giả định không chồng nhau.

**Yêu cầu:** Tổng thời gian là bao nhiêu? Nên ưu tiên tăng tốc coding hay giảm chờ và vì sao?

<details>
<summary>Gợi ý đáp án</summary>

Tổng elapsed time trong giả định không chồng nhau là **13 ngày**, với **8 ngày chờ môi trường** chiếm phần lớn. Nếu có thể tạo môi trường self-service và giảm chờ an toàn, tác động tới cycle time có thể lớn hơn chỉ tối ưu một phần nhỏ của thời gian coding. Tuy nhiên cần kiểm tra nguyên nhân chờ, năng lực và chi phí đầu tư; không suy ra một giải pháp cố định từ một item.

</details>

### Bài tập H — WIP và blocked

Workflow có 3 item Development, 2 Verification và 2 item Blocked; hai item Blocked **độc lập với hai cột trước**, tất cả đã Started chưa Done.

**Yêu cầu:** WIP tại thời điểm chốt là bao nhiêu? Nếu Blocked chỉ là nhãn của hai item Verification thì sao?

<details>
<summary>Gợi ý đáp án</summary>

Nếu Blocked là một trạng thái riêng với hai item khác, WIP = **3 + 2 + 2 = 7**. Nếu hai item Blocked chính là hai item trong Verification, WIP = **3 + 2 = 5**. Định nghĩa workflow và quy tắc đếm quyết định kết quả; không đếm trùng nhưng cũng không loại item bị chặn khỏi WIP chỉ vì chưa thể làm tiếp.

</details>

### Bài tập I — SLE và công việc xuyên nhóm

Một nhóm đặt SLE “85% item nhỏ của workflow được Done trong 10 ngày lịch”. Một item đang mở đã 14 ngày tuổi, chờ API từ sản phẩm khác.

**Yêu cầu:** SLE có nghĩa item này chắc chắn trễ cam kết không? Đội nên làm gì?

<details>
<summary>Gợi ý đáp án</summary>

SLE là kỳ vọng gồm **thời lượng và xác suất** trên loại item/workflow theo định nghĩa; không phải bảo đảm mọi item sẽ hoàn tất trước 10 ngày. Tuy nhiên item 14 ngày tuổi đáng để kiểm tra: làm rõ blocker, chủ sở hữu API, tác động tới Product Goal, lựa chọn phối hợp và dự báo. Nếu item loại khác hoặc workflow đổi, phải kiểm tra SLE còn phù hợp không. Không đóng item sớm để làm đẹp số.

</details>

### Bài tập J — Platform product hay nhóm hỗ trợ tạm?

Ba nhóm phải chờ chuyên gia bảo mật khi cấu hình một loại quyền truy cập. Những trường hợp thường gặp lặp lại, nhưng vài trường hợp rủi ro cao cần rà soát riêng.

**Yêu cầu:** Đề xuất cách giảm hàng chờ mà vẫn giữ kiểm soát.

<details>
<summary>Gợi ý đáp án</summary>

Có thể chuẩn hóa chính sách/cấu hình an toàn cho tình huống phổ biến, template kiểm tra và hướng dẫn self-service; nhóm có chuyên môn hỗ trợ xây năng lực hoặc platform hóa công cụ nếu đủ nhu cầu lặp. Các thay đổi rủi ro cao giữ đường review có thẩm quyền. Đo thời gian chờ, lỗi quyền và khả năng tự phục vụ. Không bắt buộc lập platform team mới chỉ vì có một chuyên gia; cân nhắc chi phí/vòng giá trị nội bộ và khả năng vận hành.

</details>

### Bài tập K — Scrum hay nhiều sản phẩm độc lập?

Một tổ chức có sản phẩm học viên và nền tảng Identity dùng cho năm sản phẩm. Mỗi bên có khách hàng, mức dịch vụ và thứ tự ưu tiên riêng. Lãnh đạo muốn ép mọi việc vào một Product Backlog để “đúng Scrum”.

**Yêu cầu:** Phản biện và nêu cơ chế phối hợp thay thế.

<details>
<summary>Gợi ý đáp án</summary>

Quy tắc cùng Product Backlog/PO/Goal áp dụng cho **nhiều Scrum Teams cùng một sản phẩm**. Nếu Identity là một platform product riêng phục vụ nhiều sản phẩm, có thể có backlog/owner/mục tiêu dịch vụ riêng; cần contract, chính sách ưu tiên yêu cầu, SLE/SLA nếu phù hợp và đường xử lý sự cố. Không cần ép tất cả sản phẩm thành một backlog chỉ vì cùng dùng Scrum. Nhưng cũng không nên coi Identity hoàn toàn độc lập khỏi nhu cầu của các sản phẩm tiêu thụ.

</details>

### Bài tập L — Product Goal và outcome

Nhóm ghi “Product Goal: Hoàn thành 30 API và đưa ra 20 màn hình”. Người học vẫn bị chặn sau khi đăng ký.

**Yêu cầu:** Viết lại Product Goal tập trung giá trị và chọn ba tín hiệu kiểm chứng, gồm một guardrail.

<details>
<summary>Gợi ý đáp án</summary>

Ví dụ Product Goal: **“Học viên đủ điều kiện có thể tự hoàn tất ghi danh, nhận đúng quyền và vào bài đầu mà không cần hỗ trợ trong các trường hợp chuẩn.”** Tín hiệu: (1) tỷ lệ vào bài đầu trong cửa sổ được định nghĩa, (2) thời gian từ xác nhận hợp lệ đến có thể truy cập, (3) guardrail về cấp quyền trái phép/đơn chưa xác nhận và sự cố dữ liệu. Nêu cohort, cách đếm và điều kiện chất lượng; không lấy số API thay outcome.

</details>

### Bài tập M — Đo hiệu quả sau tái tổ chức

Sau khi chuyển từ nhóm theo tầng sang nhóm theo luồng giá trị, số ticket Done tăng từ 20 lên 38 mỗi tuần, nhưng ticket được chia nhỏ hơn, Definition of Done cũng vừa được cập nhật.

**Yêu cầu:** Có thể tuyên bố năng suất tăng 90% không? Nêu cách so sánh tốt hơn.

<details>
<summary>Gợi ý đáp án</summary>

Không. Thay cách chia ticket và DoD làm đơn vị đo không nhất quán; số Done chỉ cho biết số item theo cách đếm mới. Cần định nghĩa cùng loại work item/boundary, ghi metric version, so tỷ lệ Increment đạt DoD, WIP/age/cycle time end-to-end, defect/incident và outcome người dùng. Nhân sự, độ khó, môi trường và thời kỳ quan sát cũng có thể khác; không gán nguyên nhân chắc chắn từ một báo cáo trước–sau đơn giản.

</details>

### Bài tập N — Một giải pháp tốt cần quyền ra quyết định

Product Owner ưu tiên sửa lỗi ghi danh có ảnh hưởng tới hàng trăm học viên. Nhưng nhóm vận hành platform yêu cầu mọi thay đổi pipeline phải chờ cuộc họp phê duyệt hai tuần một lần; nhóm Developers không thể điều chỉnh.

**Yêu cầu:** Hành động nào thuộc Developers, Product Owner và cấp tổ chức? Có nên bỏ hết phê duyệt không?

<details>
<summary>Gợi ý đáp án</summary>

Developers làm rõ thay đổi, test, điều kiện an toàn và phương án giảm rủi ro; Product Owner xác định mức ưu tiên và tác động giá trị; platform/service owner cùng thẩm quyền tổ chức xem liệu phê duyệt hiện tại bắt buộc hay chỉ là chính sách có thể cải tiến. Có thể tự động hóa trường hợp chuẩn và tạo đường xử lý khẩn có kiểm soát. Không tự ý bỏ điều kiện bảo mật/pháp lý chỉ để giảm chờ, nhưng cũng không giữ hàng chờ hai tuần nếu chứng cứ cho thấy có cách an toàn hơn.

</details>

### Bài tập O — Xung đột hai Sprint Goals

Team Enrollment đang làm khả năng xử lý thanh toán trùng; Team Learning đang định phát hành màn hình bài đầu phụ thuộc trạng thái quyền mới chưa ổn định.

**Yêu cầu:** Làm sao các nhóm giữ được Sprint Goals riêng mà không hy sinh Increment chung?

<details>
<summary>Gợi ý đáp án</summary>

Các Developers làm rõ hợp đồng entitlement, điều kiện test và trạng thái nguồn sự thật; thảo luận với Product Owner về thứ tự/phạm vi để không tạo UI báo thành công giả hoặc cấp quyền sai. Có thể chọn một lát cắt nhỏ dùng contract cũ tương thích, thử tích hợp sớm, hoặc điều chỉnh Sprint Backlog theo tiến triển hướng Sprint Goals. Không cần ép hai Sprint Goals thành một câu giống hệt, nhưng phải giữ Product Goal và DoD chung của một Scrum product; không tính một phần chưa đạt DoD là Done.

</details>

### Bài tập P — Incident vượt ranh giới nhóm

Một sự cố production khiến học viên A xem được đơn đăng ký của học viên B. Lỗi liên quan API ghi danh và hệ thống nhận dạng chung, mỗi đội nói rằng “phần của tôi vẫn hoạt động đúng”.

**Yêu cầu:** Đề xuất cách xử lý sự cố và hai cải tiến hệ thống sau khi giảm ảnh hưởng.

<details>
<summary>Gợi ý đáp án</summary>

Ưu tiên giảm ảnh hưởng và xử lý theo quy trình sự cố/bảo mật có thẩm quyền: xác định người điều phối, phạm vi người dùng/dữ liệu, phương án hạn chế truy cập, thông báo cần thiết và bằng chứng điều tra. Sau đó làm rõ ownership của contract xác thực/phân quyền, test API xuyên hai tài khoản và kiểm tra thay đổi schema/identity ở CI. Có thể cải thiện quan sát và đường escalation. Không dùng số ticket hoàn tất hay ranh giới phòng ban để tránh trách nhiệm với chất lượng sản phẩm.

</details>

## 21. Checklist tự đánh giá sản phẩm chung, mục tiêu chung và ranh giới nhóm

Hãy chọn **một sản phẩm thực** có nhiều nhóm cùng tham gia, trả lời bằng bằng chứng thay vì tên chức danh hoặc sơ đồ tổ chức.

### 21.1. Sản phẩm và giá trị

1. Chúng ta có mô tả **người dùng/khách hàng** cụ thể không?
2. Có biết **kết quả người dùng** nào quan trọng hơn các output kỹ thuật không?
3. Product boundary có được xác định dựa trên giá trị và quyền quyết định, không chỉ repository hoặc phòng ban không?
4. Những dịch vụ/platform dùng chung có người dùng, hợp đồng và khả năng quản trị riêng rõ không?
5. Có nhận diện sản phẩm/nhóm nào thực sự độc lập, sản phẩm/nhóm nào chỉ là một thành phần của cùng hành trình không?
6. Các stakeholders có hiểu **ranh giới bao gồm và không bao gồm** điều gì không?
7. Khi nhu cầu người dùng thay đổi, sản phẩm có cách tiếp nhận phản hồi và điều chỉnh ưu tiên không?

### 21.2. Product Goal và trách nhiệm

8. Có mục tiêu chung kiểm chứng được, không chỉ danh sách tính năng hoặc task không?
9. Product Goal có phản ánh trạng thái tương lai có giá trị của sản phẩm, nếu đội dùng Scrum không?
10. Nếu nhiều Scrum Teams cùng một sản phẩm, có **Product Goal, Product Backlog, Product Owner và Definition of Done chung** không?
11. Product Owner có **quyền quản lý thứ tự Product Backlog thật**, hay nhiều bên giao việc thẳng vào teams?
12. Vai trò phân tích/domain specialists có hỗ trợ mà không chia vụn accountability của Product Owner không?
13. Developers có tự quản cách thực hiện và kế hoạch kỹ thuật phù hợp trong giới hạn DoD không?
14. Sprint Goals của các Scrum Teams có hỗ trợ Product Goal, thay vì tranh giành nguồn lực và tạo Increment mâu thuẫn không?
15. Những quyết định vượt quyền đội (bảo mật, pháp lý, ngân sách, hạ tầng) có đường escalation minh bạch không?

### 21.3. Team boundary và năng lực

16. Một PBI có thể hoàn tất qua một nhóm hoặc phối hợp nhỏ **end-to-end**, hay luôn phải qua nhiều hàng chờ theo tầng?
17. Nhóm có đủ năng lực cross-functional trong tập thể để tạo giá trị mỗi Sprint nếu đang dùng Scrum không?
18. Những kỹ năng chuyên sâu cần dùng chung có cách hỗ trợ, phát triển năng lực hoặc cung cấp dịch vụ hợp lý không?
19. Ranh giới nhóm có xét **cognitive load** và số domain phải hiểu không?
20. Code ownership và quyền sửa module có hỗ trợ an toàn mà không tạo điểm nghẽn không?
21. Có phân biệt team boundary, component boundary và product boundary không?
22. Ranh giới được giữ đủ ổn định để nhóm học và cải tiến, nhưng có trigger xem lại khi phụ thuộc kéo dài không?

### 21.4. Backlog, phụ thuộc và phối hợp

23. Product Backlog chung có một thứ tự rõ, các view của nhóm không trở thành backlog cạnh tranh không?
24. Những PBI quan trọng có được chia thành **lát cắt giá trị**, không chỉ task UI–API–DB–QA không?
25. Refinement có mời đủ người liên quan khi có contract, dữ liệu hoặc rủi ro quan trọng không?
26. Phụ thuộc xuyên nhóm có **owner, điều kiện sẵn sàng, tác động và cách tháo chặn** không?
27. Các nhóm có phát hiện sớm API/schema mismatch và phụ thuộc đối tác không?
28. Có một chính sách thay đổi contract, version và tính tương thích phù hợp không?
29. Dịch vụ dùng chung có giảm thời gian chờ qua self-service hoặc hỗ trợ đúng nơi không?
30. Các cuộc sync liên đội có giải quyết trở ngại/ra quyết định hay chủ yếu đọc trạng thái?
31. Các Scrum events chính thức có được giữ đúng mục đích nếu vẫn dùng Scrum không?

### 21.5. Increment, chất lượng và vận hành

32. Mỗi nhóm có biết **Done của sản phẩm** khác **Done của task** thế nào không?
33. Các Scrum Teams cùng product có dùng một DoD chung để bảo vệ Increment không?
34. CI và contract/integration tests có giúp phát hiện lỗi trước khi dồn về cuối không?
35. Các ràng buộc bảo mật, dữ liệu, khả năng truy cập và vận hành có được giữ không?
36. Có cơ chế để những thay đổi nhiều nhóm tạo **Increment thực sự có thể sử dụng** không?
37. Có phân biệt **Increment đạt DoD**, **released** và **outcome** khi báo cáo không?
38. Người chịu trách nhiệm sự cố, hỗ trợ, khôi phục và thay đổi dữ liệu có rõ không?

### 21.6. Flow, phản hồi và cải tiến

39. Workflow có điểm Started/Done, work types và chính sách rõ để đo end-to-end không?
40. WIP có bao gồm item blocked thuộc boundary và tránh đếm trùng không?
41. Throughput có đếm cùng loại work item và không trộn parent/subtask một cách sai lệch không?
42. Work item age có được xem cùng cycle time để thấy những item khó chưa Done không?
43. SLE có thời lượng, xác suất và điều kiện áp dụng đúng nếu đội dùng không?
44. Chỉ số giữa các nhóm có được so với cùng định nghĩa/loại việc trước khi diễn giải không?
45. Dashboard có đi cùng dữ liệu chất lượng và **outcome người dùng** không?
46. Product Owner/stakeholders có xem được Increment tích hợp và điều chỉnh Product Backlog từ phản hồi không?
47. Có một cải tiến nhỏ với giả thuyết, owner, guardrails và mốc xem lại không?
48. Khi một thay đổi ranh giới không hiệu quả, đội có sẵn sàng sửa theo bằng chứng thay vì bảo vệ sơ đồ đã vẽ không?

Nếu nhiều câu trả lời chưa rõ, đừng bắt đầu bằng cuộc tái tổ chức toàn công ty. Hãy chọn **một hành trình người dùng đang đi qua nhiều nhóm**, làm rõ mục tiêu, quyền ưu tiên, DoD và điểm chặn, rồi thử giảm **một phụ thuộc lặp lại** với khả năng đo tác dụng.

## 22. Tổng kết

- **Ranh giới sản phẩm có trước ranh giới nhóm.** Một sản phẩm được xác định bởi giá trị, người dùng/khách hàng, stakeholders và phạm vi rõ; không suy từ số repository, module hoặc phòng ban.
- **Mục tiêu chung hướng vào kết quả người dùng**, không phải tổng số task. Product Goal trong Scrum mô tả trạng thái tương lai của sản phẩm và giúp điều hướng Product Backlog.
- **Nhiều Scrum Teams trên cùng một product** cần cùng **Product Goal, Product Backlog, Product Owner và Definition of Done** theo Scrum Guide 2020. Những sản phẩm/dịch vụ thực sự độc lập có thể cần backlog/owner riêng và hợp đồng phối hợp rõ.
- **Cross-functional không có nghĩa mỗi cá nhân biết mọi kỹ thuật**. Nhóm cần đủ năng lực trong tập thể để tạo giá trị; ranh giới tốt giảm handoff nhưng không khiến cognitive load quá sức.
- **Product Owner chịu trách nhiệm tối đa hóa giá trị và Product Backlog**, Developers tự quản cách thực hiện, Scrum Master giúp hiệu quả Scrum. Rủi ro tuân thủ/phát hành cần đúng thẩm quyền tổ chức.
- **Một Product Backlog chung không cấm views theo nhóm**, nhưng tránh các thứ tự ưu tiên độc lập mâu thuẫn cho cùng Scrum product.
- **Lát cắt dọc và contract rõ** giúp nhiều nhóm tạo Increment có thể dùng, thay vì hoàn tất lần lượt UI, API, dữ liệu và kiểm thử.
- **DoD và tích hợp liên tục bảo vệ sự thật “Done”.** Merge code, đóng task hoặc chạy một demo không đủ chứng minh một Increment chung đã hoàn tất.
- **Kanban cho thấy những điểm nghẽn xuyên nhóm** qua WIP, throughput, work item age, cycle time và SLE; phải thống nhất workflow và công bố điều kiện so sánh.
- **XP giúp giảm chi phí thay đổi nhiều nhóm** qua CI, tests, refactoring, simple design và phản hồi thường xuyên; thực hành kỹ thuật không thay quyền quyết định sản phẩm.
- **Platform nên tăng khả năng tự phục vụ** thay vì thành hàng chờ trung tâm. Một service contract rõ giúp các products phối hợp mà không buộc mọi thứ vào một backlog.
- **Cuộc họp chỉ có giá trị khi tạo quyết định và tháo trở ngại.** Không thay cơ chế tích hợp hoặc quyền rõ bằng lịch sync dày đặc.
- **Tái tổ chức là một giả thuyết cần kiểm chứng**, không phải mục đích. Trước khi đổi người, xem liệu cải thiện quyền, contract, CI, WIP hoặc năng lực đã đủ giải quyết vấn đề.
- **Đánh giá ở cấp sản phẩm và dòng giá trị**, kết hợp outcome người dùng, chất lượng, flow và độ tin cậy dữ liệu; không so vận tốc hoặc số ticket giữa nhóm như thước năng suất phổ quát.

Khi một tổ chức nói **“chúng ta cần phối hợp nhiều nhóm tốt hơn”**, hãy hỏi:

> **“Những nhóm này đang cùng tạo ra sản phẩm nào và kết quả nào cho người dùng? Ai có quyền ưu tiên toàn bộ công việc? Mỗi nhóm có thể hoàn tất được lát cắt có giá trị nào, phụ thuộc nào đang cản trở, và bằng chứng nào xác nhận Increment chung đã hoạt động đúng?”**

Trả lời những câu hỏi đó bằng sản phẩm, dữ liệu và trách nhiệm cụ thể là nền tảng để **phối hợp nhiều nhóm theo Agile mà không tạo thêm nhiều lớp quản lý chỉ để theo dõi công việc**.

## Tài liệu tham khảo định hướng

- [Manifesto for Agile Software Development](https://agilemanifesto.org/): các giá trị nền tảng về tương tác, phần mềm hoạt động, hợp tác với khách hàng và phản hồi thay đổi.
- [Principles behind the Agile Manifesto](https://agilemanifesto.org/principles.html): giao phần mềm tăng dần, cộng tác kinh doanh–kỹ thuật, các nhóm tự tổ chức, thiết kế tốt và cải tiến liên tục.
- [The Scrum Guide (2020)](https://scrumguides.org/scrum-guide.html): định nghĩa sản phẩm, Product Goal, Product Backlog, Product Owner, Scrum Teams cùng sản phẩm, Increment và Definition of Done.
- [The Kanban Guide](https://kanbanguides.org/the-kanban-guide/): Definition of Workflow, kiểm soát WIP, throughput, work item age, cycle time và Service Level Expectation.
- [Scrum.org — Scrum with Kanban](https://www.scrum.org/resources/kanban-guide-scrum-teams): cách áp dụng các thực hành Kanban để tăng khả năng quản lý flow khi đang dùng Scrum.
- **Matthew Skelton & Manuel Pais — _Team Topologies: Organizing Business and Technology Teams for Fast Flow_**: stream-aligned, platform, enabling, complicated-subsystem teams, cognitive load và các mô thức tương tác.
- **Craig Larman & Bas Vodde — _Large-Scale Scrum: More with LeSS_**: một nguồn nghiên cứu thêm về thiết kế phối hợp nhiều Scrum Teams cùng sản phẩm; không mặc định mọi tổ chức phải áp dụng LeSS.
- **Kent Beck & Cynthia Andres — _Extreme Programming Explained: Embrace Change_ (ấn bản thứ hai)**: CI, tests, simple design, refactoring, pair programming và phản hồi kỹ thuật/nghiệp vụ.
- [DORA](https://dora.dev/): nghiên cứu và thực hành về năng lực giao phần mềm và độ tin cậy vận hành; hữu ích khi đo hiệu quả tích hợp xuyên nhóm.
- [Cucumber — Gherkin Reference](https://cucumber.io/docs/gherkin/reference/): ví dụ Given–When–Then để làm rõ hành vi sản phẩm và hợp đồng giữa các thành phần, không thay kết quả test thực thi.
- **Gene Kim, Jez Humble, Patrick Debois & John Willis — _The DevOps Handbook_**: cải thiện luồng thay đổi, tích hợp/triển khai, phản hồi và cộng tác giữa phát triển–vận hành.








