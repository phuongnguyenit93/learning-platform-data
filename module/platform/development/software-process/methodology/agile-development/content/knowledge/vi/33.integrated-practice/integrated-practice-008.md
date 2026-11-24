# Thiết kế hệ thống Kanban với chính sách cùng giới hạn WIP

## 1. Mục tiêu thực hành: biến một bảng công việc thành hệ thống quản lý dòng giá trị

Trong module **AGILE_DEVELOPMENT**, chúng ta đã học cách thích ứng thông qua phản hồi sớm, giao giá trị tăng dần, user story, backlog, Scrum, Kanban, XP và các chỉ số dòng công việc. Bài **Thực hành tổng hợp** này yêu cầu áp dụng những hiểu biết ấy để thiết kế một **hệ thống Kanban có thể vận hành, đo lường và cải tiến**, chứ không chỉ vẽ ba cột To do – Doing – Done.

Một nhóm phát triển nền tảng học trực tuyến đang gặp tình huống:

- Mỗi tuần nhóm bắt đầu rất nhiều việc nhưng ít tính năng được hoàn tất tới mức người học sử dụng được.
- Những ticket ghi “Đã code” bị giữ nhiều ngày để chờ review hoặc kiểm thử tích hợp.
- Khi phát hiện lỗi đăng ký khóa, mọi người đều nhận thêm việc khẩn cấp mà không biết dừng việc nào.
- Người phụ trách sản phẩm không biết khi nào một yêu cầu có thể hoàn tất; cả nhóm chỉ báo “sắp xong”.
- Một số item bị chặn vẫn biến mất khỏi cột Doing, khiến báo cáo số việc đang làm thấp hơn thực tế.
- Họp trạng thái có rất nhiều cập nhật nhưng ít quyết định giúp công việc chảy tới Done.

**Nhiệm vụ:** Hãy thiết kế chính sách dòng công việc, bảng trực quan, giới hạn WIP, cơ chế kéo việc, cách xử lý blocker/expedite và bộ đo lường để nhóm **giảm việc mở dở, nâng khả năng hoàn tất và học từ dữ liệu thật**.

### 1.1. Sản phẩm học tập đầu ra

Kết thúc bài, người học cần có khả năng tạo và giải thích:

1. **Bản đồ dòng giá trị** cho một lớp nhu cầu người học.
2. **Definition of Workflow (DoW)** rõ điểm bắt đầu, điểm hoàn tất, đơn vị công việc và trạng thái.
3. **Bảng Kanban** thể hiện dòng công việc thực và những công việc bị chặn.
4. **Explicit policies**: điều kiện nhập/xuất trạng thái, kéo việc, review, quality, blocker, expedite và replenishment.
5. **WIP limits** được đề xuất dựa trên dữ liệu và năng lực thay vì chọn số tùy hứng.
6. **Cách đo** WIP, Work Item Age, Cycle Time, Throughput, cùng SLE có đơn vị và ranh giới rõ.
7. **Nhịp phản hồi** phù hợp: lúc nào kéo việc, hỗ trợ item già, xem chất lượng và cải tiến.
8. **Bài phân tích tình huống** khi WIP đầy, ticket blocked, yêu cầu khẩn và hàng chờ review kéo dài.
9. **Một kế hoạch thử nghiệm cải tiến** có giả thuyết, guardrails, dữ liệu và điểm xem lại.

### 1.2. Tiêu chí hoàn thành bài thực hành

Một thiết kế được xem là tốt khi người khác có thể trả lời mà không cần đoán:

- Khi nào một yêu cầu được xem là **đã bắt đầu** và lúc nào **Done**?
- Có tối đa bao nhiêu item được làm dở ở từng bước; **đang blocked có tính WIP không**?
- Khi cột phía sau đầy, người ở bước phía trước **phải làm gì**?
- Công việc nào được phép ưu tiên khẩn và ai có quyền quyết định?
- Một item có tuổi cao hơn kỳ vọng thì nhóm can thiệp như thế nào?
- Người dùng và Product Owner nhận được phản hồi ở đâu trong quy trình?
- Bằng chứng gì chứng minh việc đổi chính sách tạo cải thiện mà **không hạ chất lượng**?

Không có một sơ đồ và bộ WIP limit cố định đúng cho mọi nhóm. Bài hướng dẫn **quá trình thiết kế có lý do và điều chỉnh bằng thực nghiệm**.

## 2. Phân biệt Kanban Method, hệ thống Kanban và bảng Kanban

Một bảng có thẻ màu có thể giúp quan sát công việc, nhưng **chưa đủ tạo ra một hệ thống Kanban hữu ích**.

**Kanban Method** là một phương pháp quản lý và cải tiến cách cung cấp dịch vụ thông qua trực quan hóa công việc, giới hạn WIP, quản lý dòng chảy, làm rõ chính sách, dùng các vòng phản hồi và cải tiến có tính tiến hóa dựa trên dữ liệu.

**Hệ thống Kanban** trong bài này là tập hợp:

- **Nhu cầu/dịch vụ:** Nhóm đáp ứng loại yêu cầu nào, ai là khách hàng/người dùng?
- **Workflow:** Công việc đi qua những trạng thái nào để được coi hoàn tất?
- **Bảng trực quan:** Biểu diễn workflow và công việc ở thời điểm hiện tại.
- **WIP limits:** Những giới hạn về công việc đã bắt đầu nhưng chưa hoàn tất.
- **Chính sách tường minh:** Điều kiện nhập/xuất trạng thái, kéo việc, xử lý ngoại lệ.
- **Flow metrics và kỳ vọng dịch vụ:** Giúp nhìn tốc độ, tuổi việc, độ ổn định.
- **Feedback loops:** Các dịp quan sát, quyết định và điều chỉnh cách làm.

### 2.1. Ba mức độ trưởng thành dễ nhầm

| Tình trạng | Có gì? | Thiếu gì? |
| --- | --- | --- |
| **Danh sách task có ba cột** | Biết task chưa làm, đang làm, xong | Không rõ giới hạn, trách nhiệm với kết quả và chất lượng |
| **Workflow được trực quan hóa** | Thấy review, test, blocked, Done | Nếu không có policy và đo lường vẫn có thể bị nghẽn |
| **Hệ thống Kanban được quản lý** | Có DoW, WIP, explicit policies, flow metrics và phản hồi | Vẫn cần cải tiến liên tục; không có mô hình “xong vĩnh viễn” |

### 2.2. Đặc điểm khác Scrum

Scrum có các accountabilities, events, artifacts và commitments. Kanban có thể áp dụng để **cải thiện dòng công việc của một nhóm dùng Scrum**, của đội vận hành, hoặc của dịch vụ nhận nhu cầu liên tục. **Kanban không bắt buộc Sprint, story points hoặc vai trò Product Owner.**

Khi nhóm đang dùng Scrum, WIP limits và Work Item Age hỗ trợ Developers tập trung vào **Increment đạt Definition of Done**, chứ không thay Product Goal, Sprint Goal hoặc các sự kiện Scrum.

### 2.3. Vì sao WIP là trọng tâm?

Nếu mỗi người bắt đầu thêm một hạng mục khi gặp khó khăn, tổng WIP tăng, review/test phải chia thời gian cho nhiều item, và thời gian người dùng chờ kết quả có thể kéo dài.

**Giới hạn WIP tạo tín hiệu**: thay vì khởi động thêm, nhóm cần tìm cách **hoàn tất, gỡ blocker, review hoặc tích hợp** những việc đang mở. WIP limit không tự bảo đảm tốc độ tăng; nó đặt một ranh giới để nhóm nhìn và cải tiến hệ thống.

## 3. Chọn dịch vụ và ranh giới giá trị trước khi thiết kế bảng

Không nên bắt đầu bằng câu hỏi “bảng có mấy cột?” trước khi biết công việc đi qua hệ thống nào và kết thúc ở đâu.

### 3.1. Dịch vụ minh họa

Nhóm sản phẩm **Trải nghiệm đăng ký và học** chịu trách nhiệm giúp người học:

1. Xem và chọn một khóa miễn phí.
2. Đăng ký khóa theo tài khoản hợp lệ.
3. Nhận xác nhận đáng tin cậy.
4. Mở bài đầu tiên theo quyền.
5. Khôi phục tiến độ khi học tiếp.

**Đầu vào dịch vụ:** Các Product Backlog Items hoặc yêu cầu cải tiến đã đủ rõ để nhóm cân nhắc thực hiện.

**Đầu ra dịch vụ:** Một phần sản phẩm đạt chuẩn chất lượng đã thống nhất, được tích hợp và **có thể sử dụng** theo ranh giới hệ thống. Trạng thái **đã phát hành production** có thể được theo dõi riêng nếu release gate không trùng với Definition of Done.

### 3.2. Cần chọn điểm bắt đầu và điểm kết thúc nhất quán

Có nhiều lựa chọn hợp lệ:

| Hệ thống đo | Điểm bắt đầu | Điểm kết thúc | Phục vụ câu hỏi |
| --- | --- | --- | --- |
| **Workflow phát triển** | PBI được kéo vào trạng thái đang thực hiện | PBI đạt DoD của sản phẩm | Mất bao lâu để tạo Increment Done? |
| **Workflow từ lựa chọn tới người dùng** | Yêu cầu được cam kết đưa vào dòng | Người dùng được phép sử dụng sau release | Mất bao lâu từ quyết định tới có giá trị? |
| **Workflow hỗ trợ** | Incident/ticket được tiếp nhận xử lý | Vấn đề được giải quyết theo chính sách | Dịch vụ đáp ứng yêu cầu vận hành ra sao? |

Chọn **một ranh giới chính** cho thực hành; các mốc khác có thể đo bằng chỉ số bổ sung. Nếu vừa ghi Done sau code review vừa ghi Done sau production, thống kê Cycle Time sẽ không nhất quán.

### 3.3. Lấy ví dụ một user story theo giá trị

> “Là người học đã đăng nhập, tôi muốn đăng ký khóa miễn phí và nhận xác nhận đúng trạng thái, để bắt đầu học mà không bị nhầm lẫn.”

Công việc cần UI, API, giao dịch dữ liệu và kiểm thử xuyên hệ thống. Đừng biến mỗi kỹ thuật thành một PBI độc lập được báo Done trong khi luồng người dùng chưa dùng được.

**Nguyên tắc:** Dòng cần hướng tới **kết quả có thể kiểm chứng**, không chỉ tối ưu số ticket kỹ thuật được chuyển cột.

### 3.4. Làm rõ đối tượng yêu cầu

Đối với nhóm:

- **Người hưởng lợi trực tiếp:** Người học, giảng viên hoặc quản trị viên.
- **Người quyết định thứ tự giá trị nếu dùng Scrum:** Product Owner.
- **Developers:** Người tạo và kiểm chứng Increment theo DoD.
- **Người cung cấp năng lực hỗ trợ:** Bảo mật, nền tảng, dữ liệu, vận hành theo quyền.
- **Bên phụ thuộc:** Dịch vụ xác thực, email, kho nội dung và hệ thống quản trị.

Đừng coi mọi stakeholder là cùng một quyền. Người sử dụng có thể góp ý nhưng không tự có quyền phê duyệt thay đổi hợp đồng.

## 4. Bản đồ hóa dòng giá trị thật

Trước khi chốt board, quan sát cách **một PBI gần đây** đi từ được chọn tới Done. Phỏng vấn người thực hiện, đối chiếu ticket, PR và kết quả CI, rồi hỏi:

- Công việc nằm chờ ở đâu và vì sao?
- Có những lần bàn giao kỹ thuật hoặc quyền nào?
- Những hoạt động nào có thể diễn ra song song?
- Ở đâu thường phát hiện sai yêu cầu hoặc sai hợp đồng API?
- Có kiểm thử và phản hồi đủ sớm để tránh làm lại?
- Những bước nào là kiểm soát bắt buộc, không được bỏ?

### 4.1. Bản đồ giả định ban đầu

~~~mermaid
flowchart LR
    A["Yêu cầu sản phẩm"] --> B["Làm rõ"]
    B --> C["Ready"]
    C --> D["Phát triển UI/API/DB"]
    D --> E["Review mã và CI"]
    E --> F["Kiểm thử tích hợp"]
    F --> G["Đạt DoD"]
    G --> H["Release theo quyền"]
    H --> I["Phản hồi từ người học"]
    J["Review hợp đồng API đối tác"] -.-> D
    K["Nền tảng môi trường test"] -.-> F
~~~

Sơ đồ chưa phải bảng Kanban vì chưa có **WIP limits**, điều kiện kéo và chính sách khi bị chặn. Nó là bước thảo luận để nhìn dòng giá trị.

### 4.2. Ví dụ thời gian làm và thời gian chờ

Giả sử một PBI đã hoàn tất có những khoảng **nối tiếp, không chồng lắp**:

| Giai đoạn | Thời gian làm | Thời gian chờ |
| --- | ---: | ---: |
| Làm rõ và thiết kế hành vi | 1 ngày | 1 ngày |
| Phát triển tích hợp UI/API/data | 3 ngày | 1 ngày |
| Review và CI | 1 ngày | 3 ngày |
| Kiểm thử tích hợp, sửa lỗi | 2 ngày | 2 ngày |
| **Tổng** | **7 ngày** | **7 ngày** |

Trong ví dụ, nếu điểm bắt đầu là lúc nhóm nhận thực hiện và kết thúc sau kiểm thử đạt DoD, Cycle Time là:

\[
7+7=14\ \text{ngày làm việc}
\]

Tỷ trọng thời gian chờ trên **item này** là:

\[
\frac{7}{14}\times100\%=50\%
\]

Không được suy rằng nhân sự đã nhàn rỗi 50% thời gian. Người có thể đang làm nhiều PBI khác trong lúc một item chờ review, và đó chính là tình trạng WIP cao cần điều tra.

### 4.3. Đừng bỏ bước chỉ vì nó tạo chờ

Kiểm thử phân quyền, review migration hoặc phê duyệt môi trường có thể bắt buộc. Hãy ưu tiên **chuẩn bị sớm, self-service trong quyền, tài liệu rõ và đủ người hỗ trợ** trước khi tính chuyện xóa bước kiểm soát.

## 5. Chọn đơn vị công việc và phân loại nhu cầu

Một hệ thống Kanban cần biết **thứ gì được đếm là một work item**. Nếu một tuần đếm cả epic, PBI, subtask và bug trong một cột, throughput không còn diễn giải ổn định.

### 5.1. Đơn vị đề xuất cho workflow sản phẩm

Trong bài, đơn vị chính là **PBI có lát cắt hành vi sản phẩm**, đủ nhỏ để đi qua workflow tới DoD, có mã nhận diện riêng và chủ thể theo dõi.

Ví dụ:

| Mã | Hạng mục | Kiểu nhu cầu | Kết quả có thể kiểm chứng |
| --- | --- | --- | --- |
| K-01 | Đăng ký khóa miễn phí | User story | Đăng ký hợp lệ, xác nhận đúng |
| K-02 | Xem khóa đã đăng ký | User story | Danh sách đúng theo quyền |
| K-03 | Ngăn ghi đăng ký Active trùng | Defect/quality item | Retry/concurrency test đạt |
| K-04 | Cải thiện đường mở bài | Usability improvement | Người học tìm được bài đầu |
| K-05 | Nâng phiên bản thư viện xác thực | Technical risk reduction | Không đổi hành vi, kiểm thử bảo mật/tích hợp đạt |
| K-06 | Sự cố không mở được bài production | Incident | Dịch vụ khôi phục theo quy trình và có bằng chứng |

K-06 có thể phù hợp hơn với **workflow vận hành khác**, tùy mức độ liên quan và cách đo. Nếu đưa cả incident và PBI phát triển vào cùng bảng, nên có **phân loại và chính sách khác biệt**, không dùng một Cycle Time/SLE cho mọi loại mà không xem phân bố.

### 5.2. Epic và subtask nên được thể hiện ra sao?

- **Epic/khả năng lớn:** Theo dõi ở Product Backlog/roadmap, không mặc nhiên đếm là work item ngang một PBI nhỏ.
- **PBI:** Đơn vị dòng giá trị được kéo vào workflow và tính WIP chính.
- **Subtask:** Giúp Developers phối hợp UI/API/test; không được cộng thành throughput PBI hoặc chia nhỏ giả tạo để làm số đẹp.
- **Defect:** Có thể là item riêng nếu cần truy vết công sức và rủi ro; liên kết với PBI nếu defect làm nó chưa đạt DoD.
- **Incident:** Xử lý theo mức độ và quyền; có thể cần đường ưu tiên riêng.

### 5.3. Work item phải có thông tin tối thiểu

Một thẻ nên có:

- Mã, tiêu đề hành vi và loại nhu cầu.
- Mô tả outcome hoặc vấn đề.
- Người phối hợp/chủ sở hữu quyết định khi cần.
- Ngày bắt đầu theo DoW và thời gian đang ở trạng thái hiện tại.
- Trạng thái blocked, lý do, người có thể gỡ và mốc kiểm tra lại.
- Điều kiện Done và liên kết bằng chứng kiểm thử thích hợp.
- Loại dịch vụ/độ khẩn theo chính sách.

Không cần biến thẻ thành biểu mẫu cồng kềnh. Thông tin phải giúp **ra quyết định và hoàn tất việc**, không chỉ phục vụ kiểm soát.

## 6. Thiết kế Definition of Workflow (DoW)

**Definition of Workflow** là những đặc điểm và chính sách làm rõ hệ thống Kanban: loại item đang quản lý, điểm bắt đầu/kết thúc, trạng thái, cách item chuyển qua các trạng thái, giới hạn WIP, chính sách dịch vụ và kỳ vọng thời gian.

Trong bài, ta chọn workflow:

~~~text
Options/Backlog (chưa bắt đầu, không tính WIP)
    |
    v
Ready (cam kết xem xét, nhưng chưa kéo vào phát triển)
    |
    v  Điểm START của phép đo Cycle Time chính
Build & Integrate -> Review & CI -> Verify -> Done (DoD)
                                          ^
                                          |
                                 Điểm FINISH

Blocked = trạng thái/nhãn phủ lên item đang ở bước nào đó,
không phải cách đưa item ra khỏi WIP để làm số nhỏ đi.
~~~

**Lưu ý về Ready:** Trong ví dụ này, Ready **chưa thuộc WIP chính** vì điểm bắt đầu được đặt ở lúc kéo vào Build & Integrate. Nếu tổ chức chọn điểm bắt đầu từ Ready, phải công bố định nghĩa khác và dùng nhất quán.

### 6.1. Vì sao không đưa mọi bước vào bảng?

Bảng với 20 cột dễ làm mọi người chỉ chăm di chuyển thẻ. Chỉ nên tách một bước khi:

1. Nó phản ánh **trạng thái công việc có ý nghĩa**.
2. Có điều kiện nhập/xuất rõ.
3. Thường tạo hàng chờ hoặc quyết định riêng.
4. Việc nhìn thấy trạng thái giúp nhóm thay hành vi.

Ví dụ “Review & CI” tách vì nhóm thường có PR chờ; nếu build/test CI diễn ra hoàn toàn tự động ngay trong Build và không có hàng chờ độc lập, có thể **không cần cột riêng**.

### 6.2. Một DoW bản đầu có thể viết

| Thành phần DoW | Quyết định ban đầu |
| --- | --- |
| **Đơn vị công việc** | PBI/lát cắt sản phẩm, có loại và mã |
| **Điểm bắt đầu** | Khi item được kéo từ Ready vào Build & Integrate |
| **Điểm kết thúc** | Khi item đạt Definition of Done của sản phẩm |
| **Các trạng thái** | Ready, Build & Integrate, Review & CI, Verify, Done |
| **Blocked** | Nhãn trên trạng thái hiện hành; vẫn tính WIP |
| **Giới hạn WIP** | Đề xuất 3 Build, 2 Review & CI, 2 Verify; tổng phát triển 5 — cần làm rõ logic dưới đây |
| **Kéo việc** | Chỉ pull khi có dung lượng và chính sách cho phép |
| **Work Item Age** | Tính từ điểm START tới hiện tại khi chưa Done |
| **Cycle Time** | Tính từ START tới DoD cho item đã Done |
| **SLE** | Thiết lập từ phân bố Cycle Time lịch sử phù hợp và cập nhật theo dữ liệu |
| **Ngoại lệ** | Blocked, expedite/incident theo chính sách rõ |
| **Phản hồi** | Nhìn công việc già mỗi ngày, replenishment và service delivery review định kỳ |

### 6.3. WIP limit cột và WIP limit tổng phải tương thích

Nếu Build ≤3, Review ≤2, Verify ≤2, **tổng các giới hạn cột là 7**, không phải 5. Ta có thể đặt **hai tầng giới hạn đồng thời**:

- **Giới hạn theo trạng thái:** Build tối đa 3, Review & CI tối đa 2, Verify tối đa 2.
- **Giới hạn tổng dòng từ START tới trước Done:** **Tối đa 5 PBI**.

Vì vậy, dù từng cột chưa đầy, nhóm **không được kéo PBI thứ sáu** khi tổng WIP đang là 5, trừ khi chính sách ngoại lệ được áp dụng và ghi nhận. Hạn mức tổng không nên ghi chỉ như một con số trang trí; phải có quy tắc kiểm tra khi kéo.

### 6.4. Chọn DoD trước khi dùng chữ Done

Nếu dùng Scrum, **DoD là commitment của Increment**, không phải một ô checkbox khách hàng thích hay không. Trong hệ thống này, Done có thể đòi:

- Mã được tích hợp và kiểm tra theo chuẩn.
- Acceptance examples được kiểm chứng phù hợp.
- Unit/integration/contract tests liên quan đạt.
- Không còn lỗi dữ liệu/phân quyền thuộc điều kiện bắt buộc.
- Tài liệu/quan sát vận hành cần thiết được cập nhật.
- Increment có thể sử dụng cùng các phần trước.

**DoD phải tuân thủ các chuẩn tổ chức áp dụng.** Nếu nhiều Scrum Teams cùng một sản phẩm, chúng phải có **một DoD chung**. Không gọi Done khi một bước bắt buộc còn thiếu; cũng không mặc định phải đợi Sprint Review mới được Done.

## 7. Vẽ bảng Kanban đầu tiên có giới hạn WIP rõ

### 7.1. Bảng hoạt động minh họa

| Ready (không tính WIP) | Build & Integrate (≤3) | Review & CI (≤2) | Verify (≤2) | Done |
| --- | --- | --- | --- | --- |
| K-06 — Cải thiện tìm khóa | **K-01** — Đăng ký, 5 ngày | **K-02** — Danh sách, 7 ngày | **K-03** — Chống trùng, 8 ngày | K-00 — Xem chi tiết khóa |
| K-07 — Báo cáo tiến độ | **K-04** — Điều hướng, 2 ngày | **K-05** — Nâng thư viện, 4 ngày |  |  |
| K-08 — Thông báo lỗi rõ hơn |  |  |  |  |

Đang có **5 PBI WIP**: 2 Build + 2 Review + 1 Verify = 5. Tổng WIP đã đạt giới hạn, dù Build chưa đạt mức 3.

**Không kéo K-06 vào Build** chỉ vì có một ô trống ở cột Build. Phải giảm tổng WIP bằng cách đưa một item qua DoD hoặc xử lý ngoại lệ có thẩm quyền.

### 7.2. Khi K-03 đạt Done

Nếu K-03 đáp ứng DoD:

- Move K-03 sang Done.
- WIP từ 5 xuống 4.
- Kiểm tra item downstream cần được kéo tới Verify hay không.
- Nếu không còn pull quan trọng phía sau và tổng WIP vẫn dưới 5, **có thể** kéo một PBI Ready vào Build theo chính sách.

**Không tự động kéo K-06** nếu nó chưa đủ điều kiện Ready, thiếu quyền dữ liệu hoặc nhóm đang cần hỗ trợ review K-02.

### 7.3. Khi Review & CI có 2/2 item

Không được đẩy thêm K-01 từ Build vào Review nếu chưa có chỗ. Cách ứng xử nên cân nhắc:

1. Hỗ trợ hoàn tất review/CI của K-02 hoặc K-05.
2. Xử lý PR nhỏ và lỗi test đang ngăn di chuyển.
3. Phối hợp để item đi tới Verify nếu đủ điều kiện.
4. Nếu vấn đề nằm ở một reviewer duy nhất, thử pairing, dự phòng reviewer hoặc cải tiến kiểm thử theo chính sách.

**Đừng tạo cột “Review Pending” không giới hạn** chỉ để đẩy thẻ khỏi Build; hàng chờ vẫn tồn tại và còn khó nhìn hơn.

### 7.4. Minh họa luồng pull

~~~mermaid
flowchart LR
    A["Options / Ready"] -->|"Pull khi WIP tổng còn chỗ"| B["Build & Integrate<br/>WIP ≤3"]
    B -->|"Review có slot"| C["Review & CI<br/>WIP ≤2"]
    C -->|"Verify có slot"| D["Verify<br/>WIP ≤2"]
    D -->|"Đạt DoD"| E["Done"]
    F["Tổng WIP từ Build tới Verify ≤5"] -.-> B
    F -.-> C
    F -.-> D
    G["Blocked: nhãn trên item, vẫn tính WIP"] -.-> B
    G -.-> C
    G -.-> D
~~~

Mũi tên ghi **pull** là tín hiệu phía sau có khả năng nhận việc, không chỉ thao tác người phía trước kéo thẻ cho đẹp số.

## 8. Viết chính sách tường minh cho từng trạng thái

**Explicit policies** là lời giải thích công khai về cách dòng công việc thực sự được quản lý. Một chính sách hữu ích phải đủ rõ để người mới xử lý hai item giống nhau theo cách tương tự, nhưng không quá dài tới mức chẳng ai đọc.

### 8.1. Chính sách Ready

Một PBI được đưa vào Ready khi:

- Có câu chuyện hoặc vấn đề người dùng đủ hiểu để nhóm cân nhắc.
- Các ví dụ chấp nhận quan trọng đã được làm rõ ở mức đủ để bắt đầu.
- Phụ thuộc đáng kể và rủi ro dữ liệu đã được nhận diện.
- Không có yêu cầu phê duyệt bắt buộc còn thiếu **để được bắt đầu**.
- PBI đủ nhỏ hoặc có kế hoạch chia lát cắt, không phải epic mơ hồ.
- Thứ tự ưu tiên do người có trách nhiệm sản phẩm xác định.

**Không đòi tài liệu hoàn hảo** mới cho vào Ready. “Đủ để bắt đầu an toàn và học thêm” phù hợp hơn với điều kiện không còn bất định nào.

### 8.2. Chính sách Build & Integrate

**Entry:** PBI ở Ready; tổng WIP và WIP Build còn chỗ; nhóm có năng lực thực hiện.

**Trong trạng thái:**

- Developers cùng làm những phần UI/API/DB/test cần thiết.
- Ưu tiên PR nhỏ, tích hợp thường xuyên và phản hồi từ CI.
- Gắn blocked khi chờ môi trường, thông tin hoặc quyết định; cập nhật người có thể gỡ.
- Không chia item thành nhiều thẻ WIP giả để né giới hạn.

**Exit:** Hành vi chính được triển khai và có bằng chứng đủ cho kiểm tra tiếp theo; Review còn slot; những thiếu sót quan trọng được nêu minh bạch.

### 8.3. Chính sách Review & CI

**Entry:** Thay đổi có phạm vi rõ, CI có thể chạy, review có người chịu trách nhiệm và WIP còn chỗ.

**Trong trạng thái:**

- Reviewer xem tính đúng, rủi ro và khả năng bảo trì phù hợp.
- CI build/test theo tiêu chuẩn.
- Nếu cần sửa, item có thể quay Build theo policy và vẫn tính WIP.
- Những yêu cầu đổi API/data được trao đổi trực tiếp với người liên quan, không chờ cuộc họp tuần sau.

**Exit:** Review cần thiết và CI cho phần việc đạt, không có blocker để chuyển Verify.

### 8.4. Chính sách Verify

**Entry:** Review/CI đạt, môi trường và test data hợp lệ, Verify còn slot.

**Trong trạng thái:**

- Kiểm chứng acceptance examples, phân quyền, retry, tích hợp và các chuẩn rủi ro cần thiết.
- Test case thất bại được ghi theo bằng chứng, không rerun vô hạn để có màu xanh.
- Khi phát hiện lỗi, item có thể quay lại bước thích hợp; không được che bằng nhãn Ready/Done.

**Exit:** **Toàn bộ DoD áp dụng đạt**; Increment tích hợp sử dụng được.

### 8.5. Chính sách Done và release

**Done** khi PBI đạt DoD theo ranh giới đã định. Thời điểm hoàn tất được ghi để tính Cycle Time/throughput.

**Release** có thể sau Done khi chính sách vận hành/phát hành cho phép, với các mốc và quyền riêng. Sprint Review không phải cổng release mặc định. Nếu sản phẩm có nghiệm thu hợp đồng, cần quy trình riêng và **không coi “Done” tự là “Contract Accepted”**.

### 8.6. Bảng trạng thái, entry/exit và hoạt động khi đầy

| Trạng thái | Entry | Exit | Nếu đang đầy |
| --- | --- | --- | --- |
| Ready | Rõ giá trị, rủi ro đủ để bắt đầu | Kéo vào Build theo capacity | Tiếp tục refinement có chọn lọc, không đẩy WIP mới |
| Build | Có slot cột và tổng, PBI đủ Ready | Có thay đổi tích hợp đủ để review | Giúp item già, không mở thêm |
| Review & CI | Có slot, PR và test đầu vào rõ | Review và CI theo policy đạt | Review item cũ, hỗ trợ lỗi test |
| Verify | Có slot, bản tích hợp có thể kiểm chứng | Đạt DoD | Hoàn tất test, xử lý dữ liệu/test flaky |
| Done | Bằng chứng DoD | Không áp dụng cho dòng này | Quan sát outcome/release riêng |

## 9. Chính sách kéo việc và câu hỏi “bắt đầu hay hoàn tất?”

**Pull** không chỉ có nghĩa kéo thẻ bằng chuột. Nó là hành vi chọn việc mới dựa trên khả năng hoàn tất của hệ thống, thay vì đẩy thêm công việc vào hàng chờ.

### 9.1. Nguyên tắc ưu tiên từ phải sang trái

Trong một cuộc họp Kanban hằng ngày, nhóm có thể nhìn bảng từ Done ngược về Build:

1. Item nào đang ở Verify có thể đạt DoD hôm nay?
2. Review/CI có item nào chờ quá lâu hoặc có thể được hỗ trợ?
3. Build có item nào sắp chuyển được nhưng bị chặn bởi cột sau?
4. Tổng WIP có còn chỗ không?
5. Nếu có, item Ready nào có giá trị và ít rủi ro nhất theo chính sách ưu tiên?

Đây là **heuristic vận hành**, không phải quy định rằng người đứng ở bên phải luôn phải xử lý mọi việc bất kể chuyên môn và quyền.

### 9.2. Khi cột phía trước còn slot nhưng cột sau đã đầy

**Không khuyến khích khởi động thêm chỉ để dùng hết năng lực danh nghĩa.** Nhóm có thể:

- Cùng test và review những thay đổi đang chờ.
- Tạo test data, công cụ và tự động hóa giúp item cũ đi tiếp.
- Pair để giảm phụ thuộc một chuyên gia.
- Cải thiện CI hoặc dữ liệu cho một item đang blocked.
- Làm hoạt động không làm tăng WIP nếu chính sách cho phép, như học kỹ năng phục vụ nút nghẽn.

Nếu một người không được phép review vì lý do bảo mật hay quyền truy cập, họ không nên tự vượt quyền; cần **phối hợp người có thẩm quyền hoặc tối ưu đầu vào**.

### 9.3. Khi một item quá lớn

Một PBI “Xây toàn bộ hệ thống quản lý khóa học” có thể chiếm WIP một tháng. Hãy chia thành **các lát cắt giá trị có thể đạt DoD độc lập**, chẳng hạn:

- Hiển thị khóa công khai.
- Đăng ký khóa miễn phí.
- Xem danh sách khóa của mình.
- Mở bài đầu theo quyền.

Không cắt thành “frontend của hệ thống”, “backend của hệ thống” và “database của hệ thống” rồi gọi từng phần là Increment người dùng sử dụng được.

### 9.4. Khi không đủ kỹ năng để kéo ngay

Nếu Ready có một PBI cần migration nhưng hôm nay không có người/khả năng phê duyệt, **đừng kéo chỉ để cột Build đầy**. Làm rõ phụ thuộc, ưu tiên PBI khác đủ điều kiện hoặc lên kế hoạch phối hợp đúng quyền.

## 10. Giới hạn WIP: đặt số thử nghiệm có căn cứ

WIP limits là **chính sách để tạo hành vi và giúp học về hệ thống**, không phải các hằng số từ một bảng chuẩn.

### 10.1. Vì sao không lấy ngay “mỗi người hai việc”?

Số người không phải toàn bộ năng lực:

- Một item có thể cần nhiều người cộng tác.
- Người review hoặc kiểm thử có quyền đặc thù.
- Công việc không đồng nhất về độ lớn và rủi ro.
- Có sự cố, bảo trì và nghỉ phép.
- Hệ thống có hàng chờ liên nhóm bên ngoài.

Một số WIP theo số người chỉ là **giả thuyết ban đầu**; cần quan sát xem giới hạn đó có làm việc hoàn tất tốt hơn hay tạo tắc nghẽn giả.

### 10.2. Ba cách tìm giới hạn ban đầu

**Cách A — Từ hiện trạng và vấn đề:** Quan sát WIP trung bình/đỉnh, Work Item Age, review queue và throughput. Đề xuất giảm dần chỗ mở việc mới để xem có tăng khả năng hoàn tất.

**Cách B — Từ năng lực nút nghẽn:** Nếu một bước Verify thường chỉ xử lý được hai item đồng thời một cách hiệu quả, thử WIP Verify ≤2 và hỗ trợ đầu vào để tránh chất đống.

**Cách C — Từ số nhóm/thành viên với điều chỉnh thực tế:** Bắt đầu bằng mức vừa đủ để hỗ trợ cộng tác, rồi kiểm tra blocked time, flow và chất lượng; không coi tỷ lệ công thức là chuẩn.

### 10.3. Chính sách WIP đề xuất cho nhóm thực hành

| Vùng | Hạn mức thử | Lý do ban đầu | Tín hiệu cần quan sát |
| --- | ---: | --- | --- |
| Build & Integrate | 3 | Khuyến khích Developers hỗ trợ nhau thay vì quá nhiều PBI | Age Build, PR nhỏ, thời gian chờ |
| Review & CI | 2 | Hạn chế hàng chờ review và tập trung sửa CI | Queue age, CI failures |
| Verify | 2 | Không dồn kiểm thử vào cuối | Test lead time, blocker |
| **Tổng active** | **5** | Giảm đa nhiệm toàn dòng | Total WIP, Cycle Time, throughput |

Đây là **giới hạn thử nghiệm**, không phải kết luận tối ưu. Nhóm cần đặt thời điểm xem lại và nguyên tắc xử lý ngoại lệ.

### 10.4. Khi cột và tổng hạn mức mâu thuẫn

Ví dụ:

- Build 2/3.
- Review 2/2.
- Verify 1/2.
- Tổng WIP 5/5.

Mặc dù Build và Verify chưa đầy, **không kéo item mới** vì tổng đầy. Chỉ di chuyển item hiện có theo chính sách pull, hỗ trợ hoàn tất hoặc xử lý ngoại lệ được thống nhất.

### 10.5. WIP limit không là mục tiêu luôn phải lấp đầy

Giới hạn 5 nghĩa là **không vượt 5 trong điều kiện bình thường**, không phải phải có đúng 5 item mọi lúc. Khi cả nhóm sắp hoàn tất ba PBI hoặc đang có rủi ro bảo mật, WIP 2–3 có thể hợp lý hơn.

**Mục tiêu là làm việc chảy tới kết quả**, không tối đa hóa số thẻ trong giới hạn.

## 11. Chính sách Blocked: việc bị chặn vẫn là việc đã bắt đầu

Một sai lầm phổ biến là khi không thể tiếp tục một PBI, nhóm chuyển nó về Ready hoặc một cột “Blocked ngoài WIP” để mở ngay PBI khác. Cách này **làm WIP ảo nhỏ hơn thực tế**, che độ tuổi của item, khiến nhiều việc tồn dở và tăng chi phí chuyển ngữ cảnh.

### 11.1. Quy tắc mặc định trong bài thực hành

- Một PBI đã vượt điểm START **tiếp tục tính WIP** cho tới Done, kể cả khi blocked.
- **Work Item Age tiếp tục tăng** trong thời gian bị chặn.
- Thẻ vẫn ở trạng thái nơi nó bị chặn, có nhãn rõ ràng, lý do và thời điểm bắt đầu blocked.
- Có **người phụ trách gỡ phụ thuộc** và **điểm kiểm tra lại**, thay vì chỉ dán nhãn đỏ.
- Khi blocker biến mất, nhóm tiếp tục kéo PBI theo chính sách và ưu tiên giá trị/rủi ro.
- Nếu muốn hủy một item, phải có **chính sách hủy có lý do**, lưu dấu vết và tách khỏi số item Done; không gọi hủy là throughput.

### 11.2. Mẫu thẻ bị chặn

~~~text
ID: K-02
Tên: Danh sách khóa đã đăng ký
Workflow: Review & CI
Started: Ngày làm việc D1
Work Item Age hôm nay: 9 ngày làm việc
Blocked từ: D6
Nguyên nhân: API enrollment đổi ý nghĩa trạng thái "ACTIVE"
Ảnh hưởng: Kiểm thử quyền học và xác nhận UI chưa đáng tin
Ai có thể gỡ: Đại diện API + Developers của dòng đăng ký
Hành động tiếp: Thống nhất response contract và bổ sung contract test
Điểm kiểm tra lại: Daily Kanban tiếp theo
Lựa chọn tạm: Dùng dữ liệu giả để kiểm chứng phần không phụ thuộc,
               không gọi PBI Done nếu DoD yêu cầu API thật.
~~~

Không nên tự đưa địa chỉ cá nhân, thông tin nhạy cảm hoặc dữ liệu người học thật vào thẻ nếu quyền truy cập bảng không phù hợp.

### 11.3. Khi WIP tổng 5/5 và một item blocked

Ví dụ:

| Item | Trạng thái | Age | Blocked? |
| --- | --- | ---: | --- |
| K-01 | Build | 5 ngày | Không |
| K-02 | Review & CI | 9 ngày | **Có** |
| K-03 | Verify | 8 ngày | Không |
| K-04 | Build | 2 ngày | Không |
| K-05 | Review & CI | 4 ngày | Không |

Tổng WIP vẫn bằng **5**, không phải 4. Bước ưu tiên có thể là:

1. Kiểm tra liệu K-03 có thể đạt DoD hôm nay.
2. Gỡ blocker K-02 với người có quyền về API.
3. Hỗ trợ review/CI K-05 để chuyển tiếp khi Verify có chỗ.
4. **Không** tự kéo K-06 từ Ready vào Build chỉ để “tránh nhàn rỗi”.

Nếu blocker kéo dài bất thường, nhóm có thể cân nhắc thay đổi chính sách hoặc đưa item trở lại lựa chọn **với trạng thái hủy/tạm dừng được ghi minh bạch**; phải hiểu hệ quả trên đo lường và cam kết. Không dùng thao tác đó làm cách né WIP hàng ngày.

### 11.4. Khi blocker thuộc ngoài nhóm

Một API đối tác chưa cấp sandbox có thể không do Developers tự sửa được. Hãy làm rõ:

- Người có quyền quyết định và kênh escalation.
- Điều kiện cụ thể để phụ thuộc được coi đã hoàn tất.
- Công việc giảm rủi ro nào vẫn làm được trong quyền.
- Mốc hợp đồng/Sprint Goal nào có thể bị ảnh hưởng.
- Khi nào cần Product Owner hoặc chủ thể hợp đồng quyết định phương án khác.

**Không đổ lỗi cá nhân chỉ từ tuổi công việc lớn.** Work Item Age là tín hiệu về hệ thống, không là bảng xếp hạng người làm.

## 12. Chính sách Expedite: xử lý khẩn nhưng không biến mọi việc thành khẩn

Một người dùng không thể truy cập khóa, hoặc hệ thống đang để lộ dữ liệu tài khoản khác, có thể cần ứng cứu ngay. Kanban phải có cách phản ứng với nhu cầu khẩn mà vẫn giữ **minh bạch tác động tới những việc khác**.

### 12.1. Phân biệt mức khẩn với độ quan trọng

**Quan trọng**: chức năng giúp nhiều người học bắt đầu khóa và có giá trị lớn.

**Khẩn cấp**: nếu không xử lý ngay, thiệt hại hiện tại hoặc gần kề sẽ tăng đáng kể, chẳng hạn lỗ hổng đang bị khai thác hoặc sự cố production nghiêm trọng.

Một tính năng gợi ý khóa có giá trị lớn nhưng chưa có ngày bắt buộc không tự là expedite.

### 12.2. Chính sách expedite gợi ý

1. Chỉ những incident/rủi ro được phân loại theo **mức độ và quyền đã thống nhất** mới dùng đường expedite.
2. Đường expedite có **tối đa một item**, trừ khi quy trình ứng cứu khẩn thực tế đòi cách khác và được ghi rõ.
3. Quyết định ai có quyền kích hoạt, cách thông báo và đường huy động hỗ trợ phải được nêu trước.
4. Khi expedite bắt đầu, **nêu item nào bị gián đoạn** và điều chỉnh dự báo.
5. Expedite vẫn phải đáp ứng tiêu chuẩn chất lượng/an toàn áp dụng; nếu là incident, dùng quy trình ứng cứu phù hợp.
6. Sau khi kết thúc, xem nguyên nhân, chi phí gián đoạn và cách phòng ngừa.

### 12.3. Expedite có tính WIP không?

**Có, về bản chất đó là công việc đã bắt đầu.** Trong mô hình bài học có thể quy định:

- WIP bình thường tối đa 5.
- Có một **slot expedite ngoại lệ tối đa 1**, được kích hoạt theo quyền.
- Khi dùng slot này, **tổng WIP thực có thể lên 6**, phải thể hiện rõ 5 normal + 1 expedite.
- Không cho phép hai expedite chỉ bằng cách đổi màu thẻ.
- Sau sự cố, trở về giới hạn bình thường và xem lại công việc bị gián đoạn.

Đây là **chính sách ví dụ**, không phải chuẩn Kanban. Một số nhóm có thể chọn expedite phải chiếm một slot từ WIP hiện hữu để tránh tăng WIP; điều quan trọng là nói rõ cách tính và phản ứng, không có “công việc vô hình”.

### 12.4. Trường hợp không cần expedite

Người quản lý nhắn “ưu tiên gấp vì tôi cần demo” nhưng không có hậu quả khẩn theo chính sách. Nhóm nên thảo luận với người chịu trách nhiệm về giá trị, đổi thứ tự Ready hoặc cân nhắc trade-off trong quyền; **không tự phá WIP limit**.

### 12.5. Khi sự cố ảnh hưởng người dùng thật

Phải theo **incident response** và quyền production/security áp dụng: cô lập tác động, bảo vệ dữ liệu, đánh giá rollback, ghi nhận và phục hồi. Không bắt đợi Daily Kanban hoặc Sprint Review rồi mới ứng cứu. Kanban là công cụ minh bạch dòng công việc, không thay trách nhiệm an toàn.

## 13. Chính sách Class of Service giúp chọn thứ tự có lý do

Một hệ thống Kanban có thể sử dụng **class of service** để nêu kỳ vọng và cách xử lý các loại yêu cầu. Đây là công cụ thiết kế chính sách, không phải bắt buộc mọi đội phải có đúng bốn loại.

### 13.1. Bốn loại tham khảo

| Loại | Mục đích | Ví dụ | Chính sách |
| --- | --- | --- | --- |
| **Standard** | Hầu hết PBI có giá trị theo thứ tự ưu tiên | Cải thiện tìm khóa, mở bài | Kéo khi có slot; dùng SLE phù hợp |
| **Fixed Date** | Một phần công việc có ngày cần kết quả vì sự kiện/điều kiện thực | Chức năng phục vụ ngày khai giảng | Xem rủi ro thời hạn, giảm phụ thuộc sớm; không bảo đảm chỉ nhờ nhãn |
| **Expedite** | Vấn đề thực sự khẩn theo mức độ thiệt hại | Lỗi phân quyền production nghiêm trọng | Theo chính sách mục 12; đánh dấu tác động tới dòng thường |
| **Intangible / Improvement** | Công việc giảm rủi ro lâu dài nhưng có thể bị hoãn mãi | Nâng test CI flaky, refactoring có căn cứ | Dành capacity có chủ đích, đo tác động |

### 13.2. Không có một SLE cho mọi loại

Incident nghiêm trọng có cơ chế phản hồi khác PBI cải thiện UX. Nếu trộn mọi loại trong một phân bố Cycle Time, P85 chung có thể gây hiểu nhầm. Cân nhắc phân loại theo **workflow, loại việc và mức độ dịch vụ đủ tương đồng**.

### 13.3. Fixed Date không đồng nghĩa “đợi sát hạn rồi tăng tốc”

Nếu tính năng phải sẵn cho khai giảng, hãy:

1. Xác định điều kiện Done/release thật.
2. Tìm phụ thuộc và lead time của chúng.
3. Theo dõi Work Item Age, forecast và các dấu hiệu sớm.
4. Hoàn tất lát cắt chất lượng trước mốc nếu có thể.
5. Escalate sớm nếu điều kiện cứng có nguy cơ.

Một nhãn Fixed Date **không tự tạo capacity hoặc quyền đổi hợp đồng**.

## 14. Thiết kế chính sách Replenishment: khi nào và chọn gì để kéo

**Replenishment** là hoạt động quyết định công việc nào nên đủ điều kiện và được chọn để kéo vào dòng trong phạm vi năng lực. Nếu nhóm chỉ xử lý “ticket nào được nhắn to nhất”, WIP và giá trị dài hạn rất khó kiểm soát.

### 14.1. Các câu hỏi ở điểm bổ sung công việc

- Product Goal và nhu cầu người dùng hiện tại ưu tiên điều gì?
- Có PBI nào đã rõ, đủ nhỏ và phù hợp để làm tiếp?
- WIP tổng và các giới hạn cột có chỗ không?
- Loại công việc có SLE/chính sách riêng?
- Có một dependency nào nếu bắt đầu sớm sẽ chặn cả hệ thống?
- Có nên chia item trước khi kéo thay vì mở một epic lớn?
- Có công việc cải thiện quality/CI cần ưu tiên để tránh tắc trong tương lai?

### 14.2. Mẫu quyết định Ready

~~~text
Replenishment ngày D:
  Total WIP: 4/5
  Build: 1/3, Review: 2/2, Verify: 1/2

Ready theo ưu tiên:
  K-06 Cải thiện tìm khóa
  K-07 Báo cáo tiến độ
  K-08 Thông báo lỗi rõ hơn

Quyết định:
  Không kéo K-07 nếu đang thiếu dữ liệu test báo cáo.
  Hỗ trợ Review trước vì đang đầy và có item Age cao.
  Nếu K-03 đạt Done trong hôm nay, xem lại kéo K-06.
  Người quyết định giá trị và Developers phối hợp cập nhật backlog.
~~~

**Có slot WIP là điều kiện cần, không tự luôn là điều kiện đủ.** Nếu nút nghẽn đang ở Review, việc kéo thêm vào Build có thể tăng áp lực.

### 14.3. Nhịp replenishment không nhất thiết theo Sprint

Nhóm có thể xem công việc Ready hàng tuần, theo số slot được giải phóng hoặc khi có thay đổi lớn. **Không có lịch chuẩn bắt buộc**. Với nhóm đang dùng Scrum, Product Owner quản lý hiệu quả Product Backlog; Developers vẫn có trách nhiệm tự quản công việc để đạt Sprint Goal.

## 15. Daily Kanban: đứng trước bảng để quản lý luồng, không báo cáo từng người

Một buổi nhìn dòng công việc có thể ngắn, nhưng phải đưa ra **hành động giúp item tới Done**.

### 15.1. Câu hỏi nên dùng

1. Có item nào có thể đạt DoD hôm nay?
2. Cột downstream nào đang đầy, item nào cần giúp?
3. Item nào có Work Item Age lớn nhất và tại sao?
4. Có blocker mới hoặc cũ cần escalation?
5. Có expedite thật đang ảnh hưởng dịch vụ?
6. Có điều gì cho thấy WIP limit hiện tại bị vi phạm hoặc policy chưa rõ?
7. Có slot để pull chưa, hay nên cùng hoàn tất trước?

### 15.2. Đọc bảng từ phải sang trái

~~~text
Done <- Verify <- Review & CI <- Build & Integrate <- Ready

Ưu tiên nhìn khả năng hoàn tất ở bước phải,
sau đó mới quyết định có đủ năng lực kéo thêm từ trái.
~~~

Không bắt buộc đứng vật lý trước bảng. Với nhóm phân tán, một bảng chung được cập nhật đáng tin và trao đổi đồng bộ/bất đồng bộ phù hợp là đủ.

### 15.3. Một đoạn hội thoại minh họa

> **Người hỗ trợ:** “K-03 đang Verify 8 ngày. Có gì cản Done?”
>
> **Developer:** “Test concurrent đã sửa, nhưng trường hợp retry sau timeout còn lỗi dữ liệu.”
>
> **Người hỗ trợ:** “Ai có thể cùng xem giao dịch và test? Trong khi đó Review 2/2; ta không kéo PBI mới.”
>
> **Developer khác:** “Tôi có thể pair kiểm tra ràng buộc DB. K-05 ở Review chỉ còn CI flaky, tôi sẽ phối hợp xử lý sau.”
>
> **Người phụ trách sản phẩm:** “K-06 vẫn ở Ready; tôi chấp nhận chưa bắt đầu để tập trung hoàn tất đăng ký đáng tin.”

Buổi trao đổi giúp **đi tới quyết định và hỗ trợ**, không chấm điểm ai bận bao nhiêu.

### 15.4. Daily Scrum và Daily Kanban khi áp dụng đồng thời

Nếu nhóm là Scrum Team, **Daily Scrum là sự kiện Scrum** để Developers kiểm tra tiến bộ tới Sprint Goal và điều chỉnh Sprint Backlog. Họ có thể **dùng bảng Kanban và câu hỏi về flow ngay trong Daily Scrum**, tránh thêm hai cuộc họp trùng mục đích.

Không nên biến Daily Scrum thành một cuộc kiểm tra tuân thủ do người quản lý ra lệnh; Developers tự quản cách thực hiện.

## 16. Thiết kế feedback loops trên nhiều mức

Hệ thống Kanban chỉ hữu ích lâu dài nếu có **vòng phản hồi giúp điều chỉnh chính sách khi dữ liệu hoặc nhu cầu thay đổi**.

### 16.1. Bộ nhịp tham khảo

| Vòng phản hồi | Câu hỏi | Tần suất có thể dùng | Đầu ra |
| --- | --- | --- | --- |
| **Quan sát dòng hằng ngày** | Item nào có thể Done; bị chặn ở đâu? | Hằng ngày hoặc thường xuyên theo nhu cầu | Hỗ trợ, gỡ blocker, kéo đúng policy |
| **Replenishment** | Kéo PBI nào tiếp để phục vụ giá trị? | Khi WIP còn slot hoặc định kỳ | Ready được làm rõ, ưu tiên minh bạch |
| **Service delivery review** | Dịch vụ có ổn định và đáp ứng kỳ vọng? | Vài tuần hoặc theo dữ liệu | Xem Cycle Time, throughput, age, SLE, chất lượng |
| **Risk/operations review** | Phụ thuộc, incident và rủi ro nguồn lực nào cần xử lý? | Theo mức rủi ro | Quyết định/escalation phù hợp |
| **Strategy/product review** | Giá trị và hướng sản phẩm có còn đúng? | Theo nhịp sản phẩm | Điều chỉnh nhu cầu, class of service, capacity |
| **Operations/retrospective** | Chính sách nào đang tạo nghẽn hoặc giúp cải tiến? | Theo chu kỳ hợp lý | Thử một thay đổi và đánh giá |

Các tên nhịp là **lựa chọn thiết kế**. Không cần mỗi loại một cuộc họp cố định nếu đội nhỏ; nhiều câu hỏi có thể gộp thành một hoạt động khi đúng người và đủ thời gian.

### 16.2. Mỗi vòng phản hồi cần có quyết định

Một buổi xem CFD mà kết luận “vẫn như tuần trước” không giúp cải tiến. Hãy xác định:

- Quan sát là gì?
- Có bằng chứng nào?
- Giả thuyết nguyên nhân?
- Thay đổi chính sách nào sẽ thử?
- Guardrail và mốc xem lại?
- Ai chịu trách nhiệm làm rõ hoặc gỡ phụ thuộc?

### 16.3. Không dùng flow metrics làm KPI phạt cá nhân

Một item già có thể do API đối tác chờ phê duyệt, dữ liệu thử chưa có hoặc scope chưa rõ. Các chỉ số giúp thảo luận **độ ổn định hệ thống**, không nên gắn bảng xếp hạng “Developer nào nhanh/chậm”.

## 17. Đo WIP đúng ranh giới và tính tại một thời điểm

Trong workflow mẫu, **WIP tại thời điểm T** bằng số PBI có START rồi **chưa tới Done**.

### 17.1. Tập dữ liệu chụp bảng

| Item | Trạng thái | Đã start? | Đã Done? | Tính WIP? |
| --- | --- | --- | --- | --- |
| K-01 | Build | Có | Chưa | **Có** |
| K-02 | Review, blocked | Có | Chưa | **Có** |
| K-03 | Verify | Có | Chưa | **Có** |
| K-04 | Build | Có | Chưa | **Có** |
| K-05 | Review | Có | Chưa | **Có** |
| K-06 | Ready | Chưa | Chưa | **Không** |
| K-00 | Done | Có | Có | **Không** |

**WIP = 5**, trong đó **một item blocked**. Đừng trừ blocked khỏi WIP.

### 17.2. Lỗi đếm thường gặp

- Đếm subtask UI, API và DB cùng PBI mẹ thành bốn item.
- Đếm item Ready chưa qua điểm START vào WIP, trong khi DoW nói Ready không tính.
- Bỏ item blocked ra khỏi WIP để báo cột thấp.
- Giữ item đã Done ở trạng thái Verify vì chờ Sprint Review, khiến Cycle Time không còn đúng ranh giới.
- Gộp incident và PBI rất khác nhau rồi so throughput không phân loại.

### 17.3. WIP trung bình khác WIP chụp ảnh

WIP tại D10 là 5; đó không tự là **WIP trung bình cả tháng**. Muốn tính trung bình, phải có dữ liệu WIP theo thời điểm hoặc quy trình lấy mẫu, nêu rõ lịch làm việc/ngày nghỉ và ranh giới.

Một snapshot đơn lẻ không chứng minh hệ thống luôn ở mức 5.

## 18. Work Item Age: tín hiệu mạnh nhất cho hạng mục chưa hoàn tất

**Work Item Age** là khoảng thời gian trôi qua từ điểm START của item **chưa Done** tới thời điểm xem.

Không nhầm với:

- **Cycle Time:** Tính cho item đã Done.
- **Lead Time:** Có thể dùng ranh giới từ yêu cầu/commitment tới sử dụng; phải định nghĩa.
- **Thời gian trong cột:** Chỉ thời gian ở trạng thái hiện tại, không thay tổng tuổi item.
- **Tỷ lệ hoàn thành:** Tuổi 9 ngày không có nghĩa PBI đã 90% xong.

### 18.1. Bảng tuổi item thực hành

Giả sử WIP chính có SLE tham khảo **85% item hoàn tất trong không quá 10 ngày làm việc**.

| Item | Age | Trạng thái | So với mốc 10 ngày | Quyết định cần xem |
| --- | ---: | --- | ---: | --- |
| K-01 | 5 ngày | Build | 50% mốc thời gian | Có blocker nào đang hình thành? |
| K-02 | 9 ngày | Review, blocked | 90% mốc thời gian | Gỡ blocker API và hỗ trợ review |
| K-03 | 8 ngày | Verify | 80% mốc thời gian | Ưu tiên test còn thiếu để đạt DoD |
| K-04 | 2 ngày | Build | 20% mốc thời gian | Tiếp tục nếu không cản item già |
| K-05 | 4 ngày | Review | 40% mốc thời gian | Xử lý CI/flaky test |

Cột phần trăm là **Age/SLE threshold**, chỉ mức tiến gần mốc thời gian tham khảo; **không phải phần trăm công việc Done hoặc xác suất hoàn tất**.

### 18.2. Vì sao K-02 phải được chú ý?

K-02 đã có Age 9 ngày và blocked ở Review. Nếu hôm nay chỉ bắt đầu thêm một item từ Ready, Age K-02 vẫn tăng và người học tiếp tục chờ. Cần hỏi:

- Phụ thuộc chính xác là gì?
- Có thể làm rõ API contract trong ngày không?
- Ai có thể review hoặc pair?
- Những kiểm tra còn thiếu là bắt buộc hay do test flaky?
- Có ảnh hưởng Product Goal/mốc không?

### 18.3. Đừng tính “thời gian còn lại = SLE − Age”

Nếu Age 12 ngày và SLE P85 10 ngày, không được viết “còn -2 ngày”. Khi item tồn tại tới 12 ngày, phân bố thời gian còn lại **có điều kiện trên việc chưa Done**, không suy trực tiếp từ một phân vị của Cycle Time.

SLE không phải deadline tuyệt đối hay giới hạn thời gian vật lý; nó là **kỳ vọng dịch vụ được tạo từ dữ liệu và chính sách**.

### 18.4. Aging WIP Chart

Một biểu đồ Aging WIP có thể đặt các trạng thái workflow theo trục ngang và **tuổi item chưa Done** theo trục dọc, với đường/range tham khảo từ SLE hoặc phân vị lịch sử.

Biểu đồ giúp phát hiện item già đang nằm ở đâu; nó không tự chỉ ra nguyên nhân. Dữ liệu cần được bổ sung bằng **blocker, độ phức tạp, loại item và trao đổi với người thực hiện**.

## 19. Cycle Time: đo thời gian hoàn tất mà không che item dở

Theo DoW mẫu, Cycle Time tính từ **lúc kéo PBI vào Build** đến **lúc đáp ứng DoD**.

### 19.1. Tập dữ liệu 20 PBI đã Done

Giả sử các Cycle Time theo ngày làm việc, đã xếp tăng:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

Đây là dữ liệu giả định. Thực tế cần xác minh các item có tương đồng và quá trình đo có nhất quán không.

### 19.2. Phân vị nearest-rank từng bước

Với \(n=20\) item:

**Trung vị:** Giá trị thứ 10 và 11 đều là 6; median bằng **6 ngày làm việc**.

**P85 nearest-rank:**

\[
r_{85}=\lceil 0{,}85\times20\rceil=\lceil17\rceil=17
\]

Giá trị ở vị trí 17 là **10 ngày**.

**P95 nearest-rank:**

\[
r_{95}=\lceil 0{,}95\times20\rceil=19
\]

Giá trị vị trí 19 là **13 ngày**.

| Thước đo | Giá trị minh họa | Ý nghĩa |
| --- | ---: | --- |
| Median | 6 ngày | Một nửa quan sát ≤6 ngày trong mẫu |
| P85 | 10 ngày | 17/20 item trong mẫu hoàn tất ≤10 ngày |
| P95 | 13 ngày | 19/20 item trong mẫu hoàn tất ≤13 ngày |
| Max | 18 ngày | Có ít nhất một item ở đuôi dài |

### 19.3. Không đọc P85 như lời hứa cho từng PBI

Trong mẫu, \(17/20=85\%\) PBI đạt ≤10 ngày. Điều đó không có nghĩa **mọi PBI mới có xác suất độc lập và chính xác 85%**, nhất là khi có thay đổi WIP, nhân sự, độ phức tạp, loại item hoặc phụ thuộc bên ngoài.

Các phương pháp tính phân vị khác có thể cho kết quả nội suy khác; bài dùng **nearest-rank** để rõ ràng.

### 19.4. Survivor bias của các item đã Done

Nếu chỉ xem Cycle Time của item đã Done và quên những item WIP tuổi 16–25 ngày, bức tranh có thể lạc quan giả.

**Luôn xem Work Item Age cùng Cycle Time**, đặc biệt trước những mốc Product Goal hoặc sự kiện fixed date.

## 20. Thiết lập Service Level Expectation (SLE) có cơ sở

Trong hệ thống Kanban, **Service Level Expectation** mô tả kỳ vọng có xác suất về thời gian một item đi qua workflow đã định nghĩa.

### 20.1. SLE thử nghiệm từ mẫu

Với 20 Cycle Time minh họa, nhóm có thể viết:

> **SLE ban đầu cho PBI tiêu chuẩn:** Khoảng 85% hạng mục được hoàn tất từ lúc bắt đầu Build tới DoD trong **không quá 10 ngày làm việc**, dựa trên 20 item gần đây theo ranh giới đã xác định.

Đây là **kỳ vọng dịch vụ**, không phải SLA hợp đồng hoặc deadline đảm bảo. Cần nêu loại item, ranh giới, đơn vị và nguồn dữ liệu.

### 20.2. Khi chưa có dữ liệu đủ tốt

Nhóm có thể đưa ra **SLE dự kiến có giả định**, ghi rõ chưa phải kỳ vọng được hiệu chuẩn bằng lịch sử; sau khi có dữ liệu phù hợp thì cập nhật.

Không nên bịa một P85 chính xác từ ba item hoặc từ cảm giác “mỗi người làm 2 ngày”.

### 20.3. Khi WIP giảm nhưng SLE lịch sử chưa phản ánh

Giảm WIP có thể thay đổi Cycle Time trong tương lai, nhưng **không tự sửa kết quả lịch sử**. Nên giữ SLE hiện tại như đường quan sát tạm, thu thêm dữ liệu rồi đánh giá một cách nhất quán.

### 20.4. Khi loại item quá khác nhau

Một incident critical hoặc yêu cầu migration phức tạp có thể cần chính sách/kỳ vọng khác user story tiêu chuẩn. Phân loại có ý nghĩa khi dữ liệu và cách vận hành khác thực, không để nhóm **chia loại chỉ để làm SLE trông đẹp**.

### 20.5. Phản ứng với item gần hoặc vượt SLE

- Nhìn Age và trạng thái blocked.
- Tìm cách hỗ trợ những item gần Done.
- Xác minh nguyên nhân hệ thống: review, môi trường, dữ liệu, phụ thuộc.
- Thông báo rủi ro với Product Owner/stakeholder khi có tác động mốc.
- Ghi lại để xem trong service delivery review.

**Không cố gắng “đạt SLE” bằng cách giảm DoD, chuyển item khó về Ready hoặc đóng ticket chưa hoàn tất.**

## 21. Throughput và dự báo với dữ liệu không đồng đều

**Throughput** là số item đạt Done trong một khoảng thời gian theo DoW. Khi dùng cho dự báo, cần nhớ số item không tự phản ánh kích thước và loại công việc.

### 21.1. Dữ liệu sáu tuần minh họa

~~~text
Tuần 1: 3 PBI Done
Tuần 2: 5 PBI Done
Tuần 3: 4 PBI Done
Tuần 4: 2 PBI Done
Tuần 5: 6 PBI Done
Tuần 6: 4 PBI Done
~~~

Throughput trung bình:

\[
\bar T=\frac{3+5+4+2+6+4}{6}=4\ \text{PBI/tuần}
\]

Nếu còn 16 PBI tương tự, phép chia \(16/4=4\) tuần là **tham khảo thô**, không phải mốc chắc chắn. Mẫu dao động 2–6 PBI/tuần, có phụ thuộc và chất lượng phải đạt.

### 21.2. Khi nên dùng mô phỏng

Với dữ liệu đủ đại diện, có thể dùng **Monte Carlo forecasting** dựa trên throughput để mô tả phân bố thời gian hoàn tất:

1. Lấy mẫu throughput thực từ những kỳ tương đồng.
2. Định nghĩa số item còn lại và điều kiện được coi Done.
3. Mô phỏng nhiều chuỗi kỳ tương lai bằng những giả định rõ.
4. Ghi kỳ đạt số item cần thiết trong từng chuỗi.
5. Tổng hợp phân bố và nói rõ giới hạn mô hình.

Không tự công bố “85% chắc chắn giao trong 4 tuần” từ trung bình đơn giản. Chỉ số phục vụ **quyết định và quản trị bất định**, không thay cam kết hợp đồng.

### 21.3. Throughput tăng chưa chắc tốt hơn

Nhóm có thể tăng throughput bằng cách chia item thật nhỏ nhưng không tạo giá trị end-to-end, bỏ test hoặc chỉ chọn việc dễ. Vì vậy cần đọc cùng:

- **Độ hoàn tất của Increment/DoD.**
- **Cycle Time và Work Item Age.**
- **Lỗi và khả năng vận hành.**
- **Outcome người học**: đăng ký thành công, mở bài, tiếp tục học.

## 22. Little's Law: hỗ trợ tư duy giới hạn WIP nhưng không phải máy tính deadline

Trong một hệ thống **ổn định theo điều kiện phù hợp** và cùng ranh giới, quan hệ Little's Law có dạng:

\[
\overline{WIP}
=
\overline{Throughput}
\times
\overline{Cycle\ Time}
\]

Nếu WIP trung bình bằng 8 item và throughput trung bình bằng 4 item/tuần, Cycle Time trung bình liên hệ khoảng:

\[
\frac{8}{4}=2\ \text{tuần}
\]

Đây là **quan hệ trung bình**, không cho P85 hay thời gian còn lại của từng item. Nếu đầu vào/đầu ra thay đổi mạnh, hệ thống tăng tồn đọng, hoặc định nghĩa WIP/Done khác nhau, không được tùy tiện dùng phép chia để tuyên bố kết quả.

### 22.1. Vì sao đặt WIP limit có thể giúp?

Giảm số item mở song song có thể giúp:

- Ít chuyển ngữ cảnh.
- Review/test tập trung vào item đang chờ.
- Phát hiện blocker sớm.
- Tăng cơ hội hoàn tất trước khi bắt đầu thêm.

Nhưng nếu WIP limit quá thấp so với nhu cầu song song thật hoặc cản một phụ thuộc cần chạy đồng thời, throughput có thể giảm. **Phải đo và điều chỉnh**, không coi giảm WIP càng nhiều càng tốt.

### 22.2. Đừng suy “WIP giảm một nửa thì throughput gấp đôi”

Little's Law không khẳng định như vậy. Nó mô tả mối quan hệ giữa **ba đại lượng trung bình dưới những điều kiện nhất định**. Throughput còn chịu ảnh hưởng của năng lực, độ phức tạp, chất lượng và phụ thuộc.

### 22.3. Guardrail khi thay giới hạn

Khi thử giảm tổng WIP 7 xuống 5, cần theo dõi:

- Cycle Time của những item đã Done và Age của item còn dở.
- Throughput và các kỳ thiếu nguồn việc hợp lệ.
- Chất lượng/defect, lỗi production và DoD.
- Tình trạng blocker và thời gian chờ review.
- Sức bền làm việc và việc phải làm thêm ngoài giờ.

Không kết luận thành công chỉ từ bảng bớt thẻ.

## 23. Cumulative Flow Diagram (CFD): nhìn chỗ đang tích tụ công việc

**Cumulative Flow Diagram** biểu diễn số lượng công việc tích lũy theo các trạng thái workflow qua thời gian. Nó có thể giúp người xem thấy:

- Khối lượng tồn ở các vùng workflow.
- Một vùng đang dày lên và có khả năng tạo hàng chờ.
- Sự thay đổi của dòng vào và dòng ra.
- Dấu hiệu cần kiểm tra WIP, thời gian chờ và chính sách kéo việc.

CFD **không tự chỉ rõ nguyên nhân**. Một vùng Review dày lên có thể do thiếu reviewer, CI flaky, kiểm soát dữ liệu bắt buộc hoặc loại PBI đang khó hơn.

### 23.1. Một bảng dữ liệu giả định để bàn về CFD

Để tránh nhập nhằng cách vẽ, bảng sau dùng **số item tại cuối ngày**, không phải các dải số tích lũy. Nó giúp nhận ra xu hướng WIP trước khi chuyển sang vẽ CFD:

| Ngày | Build | Review & CI | Verify | Tổng WIP | Done tích lũy |
| --- | ---: | ---: | ---: | ---: | ---: |
| D1 | 2 | 1 | 0 | 3 | 0 |
| D2 | 2 | 2 | 1 | 5 | 0 |
| D3 | 2 | 2 | 1 | 5 | 1 |
| D4 | 1 | 2 | 2 | 5 | 2 |
| D5 | 2 | 1 | 1 | 4 | 4 |

Các snapshot phù hợp với thử nghiệm tổng WIP ≤5 và giới hạn cột đã định. Cần lưu ý số Done tích lũy tăng khi item đạt DoD, và số đầu vào/di chuyển phải được theo dõi để giải thích biến động.

### 23.2. Chuyển snapshot thành vùng tích lũy

Đối với một workflow đơn giản không có nhiều vòng quay, có thể biểu diễn biên các vùng bằng **số item tích lũy tới từng trạng thái**; trục thời gian nằm ngang, trục số lượng item dọc. Ví dụ tại D5:

- Done tích lũy: 4.
- Done + Verify: \(4+1=5\).
- Done + Verify + Review: \(4+1+1=6\).
- Done + Verify + Review + Build: \(4+1+1+2=8\).

Độ rộng theo chiều số lượng giữa các biên là số item đang ở trạng thái tương ứng. Cách chuẩn bị dữ liệu thực phải xử lý rõ item hủy, chuyển lại, cùng đơn vị đếm và lịch sử workflow.

### 23.3. Khi vùng Review mở rộng

Nếu trong nhiều ngày:

- Build vẫn liên tục đẩy item ra.
- Review & CI không đủ khả năng chuyển sang Verify.
- Tổng WIP tăng hoặc các item Review có Age cao.

Nhóm cần hỏi **vì sao Review không thông suốt**: PR quá lớn, quá ít người review, hợp đồng API không rõ, CI đỏ hoặc môi trường test lỗi? Quyết định có thể là giảm kéo PBI mới, review theo cặp, sửa CI hoặc thay cách chia lát cắt.

### 23.4. CFD và Aging WIP bổ sung nhau

CFD có thể thấy **vùng nào tích tụ**, còn Aging WIP có thể cho biết **item nào đang già**. Một vùng nhỏ vẫn có một item 25 ngày bị chặn; chỉ nhìn bề dày vùng sẽ dễ bỏ sót.

Không dùng CFD như “chứng minh năng suất cá nhân” hoặc kết luận nguyên nhân chỉ từ hình dạng.

## 24. Flow Efficiency: tỷ lệ thời gian làm và thời gian chờ

Một thước đo có thể giúp nhóm đặt câu hỏi về hàng chờ là **Flow Efficiency**, thường biểu diễn tỷ lệ thời gian làm việc trực tiếp trên tổng thời gian trôi qua của một item, với **quy tắc phân loại rõ**.

Trong ví dụ ở mục 4:

- Thời gian làm: 7 ngày.
- Thời gian chờ: 7 ngày.
- Tổng thời gian trôi qua: 14 ngày.

Ta có:

\[
\text{Flow Efficiency}
=
\frac{7}{14}\times100\%
=50\%
\]

### 24.1. Cần định nghĩa “thời gian làm” trước

Trong thực tế, một hoạt động có thể:

- Diễn ra song song với hoạt động khác.
- Bị gián đoạn nhiều lần trong ngày.
- Có bước review chủ động xen thời gian đợi reviewer.
- Được thực hiện bởi nhiều người trên cùng item.

Nếu không có cách ghi phù hợp, một tỷ lệ 50% có thể chỉ là ước lượng. **Không bắt đội theo dõi từng phút** nếu chi phí ghi nhận lớn hơn giá trị phân tích.

### 24.2. Flow Efficiency không là KPI phải luôn tăng

Một bước kiểm thử an toàn bắt buộc có thể thêm thời gian nhưng giảm lỗi production. Việc “bỏ test để tăng Flow Efficiency” là đánh đổi sai. Cần xem **chất lượng và giá trị người dùng cùng thời gian chờ**.

### 24.3. Hành động có thể hữu ích hơn tính tỷ lệ

Đôi khi chỉ cần biết “Review chờ 3 ngày vì một reviewer duy nhất” đã đủ để thử chính sách reviewer dự phòng hoặc giảm PR lớn. Không cần nhiều chữ số sau dấu phẩy mới ra được quyết định.

## 25. Mô phỏng vận hành bảng trong năm ngày

Phần này ghép **DoW, WIP limits, pull, blocked, SLE và phản hồi** thành chuỗi quyết định.

### 25.1. Điều kiện ban đầu

Chính sách:

- Build ≤3; Review & CI ≤2; Verify ≤2.
- Tổng WIP từ Build tới trước Done ≤5.
- Item blocked vẫn tính WIP.
- Chỉ kéo Ready khi có năng lực và dưới tất cả giới hạn liên quan.
- Một expedite ngoài hạn mức thường chỉ khi incident/rủi ro được phân loại theo quyền.
- Item đạt DoD được chuyển Done ngay, không chờ Sprint Review.

Snapshot D1:

| Vùng | Thẻ |
| --- | --- |
| Ready | K-06, K-07, K-08 |
| Build | K-01, K-04 |
| Review | K-02 |
| Verify | Chưa có |
| Done | Chưa có |

Tổng WIP **3/5**.

### 25.2. Ngày D1 — có slot nhưng nên nhìn downstream trước

Trong Daily Kanban, nhóm thấy K-02 ở Review đã chờ vì contract API chưa rõ. Một người muốn kéo K-06 vào Build ngay vì tổng chỉ 3/5.

**Quyết định tốt hơn:** Trước hết xác định ai có thể gỡ contract K-02, đồng thời cân nhắc K-01 có thể chuyển Review không. Nếu vẫn còn capacity và Ready thực sự đủ điều kiện, **có thể kéo K-06**. Hạn mức là tối đa, không cấm mọi khởi động mới, nhưng không nên phớt lờ blocker.

**Điều phải ghi:** Nếu K-06 được kéo thì WIP tăng; K-02 vẫn WIP dù blocked.

### 25.3. Ngày D2 — Review đầy

Giả sử tới cuối D2:

- Build: K-01 và K-04.
- Review: K-02 và K-05.
- Verify: K-03.
- Tổng WIP: 5/5.

**Sự kiện:** K-01 được chuẩn bị review, nhưng Review đã 2/2. Nếu nhóm đẩy K-01 vào Review bằng cách tạo một “cột pending vô hạn”, chính sách bị vô hiệu.

**Hành động:** Hỗ trợ chuyển K-05 qua Verify khi có slot, sửa CI nếu cần; ưu tiên hoàn tất K-03 nếu Verify có khả năng Done. K-01 vẫn tính WIP ở Build, không được báo “gần xong” như Done.

### 25.4. Ngày D3 — PBI Verify đạt DoD

K-03 đạt đầy đủ DoD và chuyển sang Done. Tổng WIP từ 5 xuống 4, **throughput của D3 tăng thêm 1** theo điểm kết thúc đã định.

Sau đó:

1. Verify có slot.
2. K-05 có thể được kéo từ Review sang Verify **nếu** tiêu chí exit Review/entry Verify đạt.
3. Review có slot nên K-01 có thể chuyển từ Build sang Review **nếu** có đủ bằng chứng.
4. Tổng WIP vẫn 4 nếu chỉ di chuyển các item đang mở.
5. Chỉ cân nhắc kéo thêm Ready khi các bước trên và nhu cầu hỗ trợ đã rõ.

### 25.5. Ngày D4 — blocker API vẫn chưa giải quyết

K-02 hiện có Work Item Age cao và vẫn chờ hợp đồng trạng thái enrollment. Mặc dù các item khác đang tiến triển, nhóm không nên:

- Đưa K-02 về Ready không có quyết định.
- Tự gọi K-02 Done.
- Kéo thêm nhiều PBI để bù một việc đang chờ.

Nên **escalate với người chịu trách nhiệm API**, làm rõ điều kiện giải tỏa blocker, xem tác động tới Product Goal và mốc, đồng thời làm phần kiểm chứng an toàn không phụ thuộc.

### 25.6. Ngày D5 — một sự cố production nghiêm trọng

Người học báo có thể nhìn dữ liệu đăng ký của tài khoản khác. Theo chính sách sự cố đã thống nhất, nhóm kích hoạt **một expedite** và xử lý ngay theo quyền security/incident.

Nếu WIP thường đang 4, thêm expedite tạo **5 item WIP thực**; nếu WIP thường đang 5, có thể tạo 6 theo chính sách ngoại lệ (5 normal + 1 expedite). Trạng thái bảng và báo cáo phải thể hiện rõ, cùng những item đang bị gián đoạn.

Không được áp dụng “expedite” chỉ để né kiểm thử phân quyền. Trong sự cố, ưu tiên bảo vệ dữ liệu, giảm tác động, khôi phục và ghi nhận bằng chứng; sau đó xem lại nguyên nhân và chính sách.

### 25.7. Đánh giá chuỗi ngày

Những câu hỏi nhóm cần trả lời sau D5:

- Bao nhiêu item thật sự Done?
- Mức WIP từng ngày có đúng cả giới hạn cột và giới hạn tổng?
- K-02 blocked mấy ngày, ai có thể gỡ?
- Có bao nhiêu lần người làm muốn kéo thêm chỉ vì một cột còn chỗ?
- Expedite làm gián đoạn những PBI nào?
- Điều gì có thể cải thiện ngay mà không cần đổi tổ chức?
- Kết quả người học có cải thiện hay chỉ có nhiều thẻ di chuyển?

## 26. Tình huống mở rộng: chất lượng đăng ký không được đánh đổi để tăng throughput

### 26.1. Điều kiện nghiệp vụ

Nhóm có PBI K-03: **“Ngăn đăng ký đang có hiệu lực bị ghi trùng do retry và concurrency.”** Một Developer sửa endpoint và thấy unit test thông thường đều xanh.

Tại Verify, kiểm thử đồng thời với DB thật trong môi trường thử phát hiện **hai bản ghi Active** cùng tài khoản và khóa khi hai request gần đồng thời.

Nếu nhóm chỉ nhìn số item Done/tuần, họ có thể bị cám dỗ:

> “Chuyển K-03 sang Done để giữ throughput; còn test concurrent sửa sau.”

Đó là hành vi phá **DoD và niềm tin vào dữ liệu Kanban**.

### 26.2. Acceptance examples qua Gherkin

~~~gherkin
Tính năng: Đăng ký khóa học miễn phí đáng tin

  Tình huống: Một lần đăng ký hợp lệ
    Cho trước người học đã đăng nhập
    Và khóa "Java nhập môn" đang cho phép đăng ký miễn phí
    Và người học chưa có đăng ký đang có hiệu lực
    Khi người học gửi yêu cầu đăng ký
    Thì hệ thống lưu đúng một đăng ký đang có hiệu lực
    Và giao diện hiển thị trạng thái xác nhận đáng tin

  Tình huống: Hai yêu cầu gần đồng thời
    Cho trước người học chưa có đăng ký đang có hiệu lực của khóa
    Khi hai yêu cầu đăng ký cùng khóa đến gần đồng thời
    Thì hệ thống không tạo hai đăng ký đang có hiệu lực trùng nhau
    Và phản hồi của từng yêu cầu tuân hợp đồng API đã thống nhất

  Tình huống: Timeout chưa xác định kết quả lưu
    Cho trước client chưa biết server có hoàn tất thao tác ghi hay chưa
    Khi người học kiểm tra trạng thái đăng ký
    Thì giao diện không báo chắc chắn đã đăng ký thành công nếu chưa xác minh
    Và có đường kiểm tra trạng thái hoặc thử lại phù hợp

  Tình huống: Người học không đọc được dữ liệu tài khoản khác
    Cho trước tài khoản A đã đăng nhập
    Và một đăng ký thuộc tài khoản B
    Khi A cố truy cập đăng ký của B
    Thì hệ thống từ chối theo quy tắc phân quyền
    Và không tiết lộ dữ liệu riêng của B
~~~

Những kịch bản là **mô tả hành vi**, không tự trở thành test đã chạy. Cần kiểm thử ranh giới API–DB, quyền truy cập, dữ liệu và môi trường phù hợp. Khi test quan trọng thất bại, K-03 **chưa Done**, vẫn thuộc WIP và cần ưu tiên hoàn tất.

### 26.3. Tín hiệu Kanban cần xem

- K-03 đang Verify bao lâu?
- Nó có làm Verify đầy 2/2?
- Có cần pair với người hiểu giao dịch dữ liệu?
- Việc sửa có tạo thay đổi hợp đồng với nhóm API khác?
- Work Item Age có tăng gần/vượt SLE?
- Có thể giảm pull mới để tập trung sửa chất lượng?

### 26.4. Không nhầm defect và công việc bổ sung

Nếu K-03 là lỗi của PBI chưa đạt DoD, không nên đóng PBI gốc rồi tạo một defect “để sau” chỉ để tăng throughput. Nếu là defect phát hiện sau release ở chức năng trước đó, nhóm có thể tạo item riêng và phân loại mức độ/rủi ro phù hợp; **không che tác động người dùng thật**.

## 27. Kết hợp Kanban với Scrum, XP và backlog theo giá trị

Kanban không bắt buộc thay Scrum hoặc XP. Hệ thống flow có thể giúp những thực hành hiện hữu hoạt động hiệu quả hơn.

### 27.1. Nếu nhóm dùng Scrum

| Thành phần Scrum | Kanban hỗ trợ thế nào? | Không nên làm gì? |
| --- | --- | --- |
| **Product Goal** | Giúp nhìn PBI phục vụ hướng giá trị và tốc độ tới Increment | Đổi Product Goal thành mục tiêu số ticket |
| **Product Backlog** | Duy trì options/Ready có thứ tự theo giá trị và rủi ro | Để mọi PBI trở thành WIP ngay khi được ghi |
| **Sprint Goal** | Tập trung giảm WIP và hoàn tất những PBI góp phần đạt Goal | Tùy tiện kéo việc không liên quan khiến Goal gặp nguy hiểm |
| **Sprint Backlog** | Developers nhìn flow, blockers và điều chỉnh cách làm | Biến bảng thành công cụ giám sát từng người |
| **Daily Scrum** | Dùng Age, blocked, WIP để kiểm tra tiến bộ và thích ứng | Thêm một cuộc Daily Kanban trùng mục đích không cần thiết |
| **Increment/DoD** | Đặt Done là trạng thái chất lượng thật | Gọi Done khi chỉ code xong hoặc đợi Review mới Done |
| **Sprint Review** | Dùng dữ liệu delivery và outcome để inspect & adapt | Trở thành cổng release mặc định |
| **Retrospective** | Chọn thử chính sách WIP, review, test dựa trên bằng chứng | Chỉ họp kể lỗi mà không có thí nghiệm |

### 27.2. Nếu nhóm dùng Kanban không có Sprint

Có thể replenishment theo slot được giải phóng, review dịch vụ định kỳ và cập nhật ưu tiên khi nhu cầu mới đến. Vẫn cần **mục tiêu dịch vụ, chất lượng và cơ chế phản hồi**, không chỉ liên tục nhận ticket.

### 27.3. XP giúp giảm tắc nghẽn kỹ thuật

- **Continuous Integration:** Phát hiện xung đột sớm trước khi PR nằm chờ.
- **TDD:** Kiểm chứng nghiệp vụ ở mức phù hợp.
- **Pair programming:** Chia sẻ kiến thức và cùng gỡ item già.
- **Refactoring:** Giữ khả năng thay đổi mà không phá hành vi đã kiểm chứng.
- **Small releases:** Đưa Increment đủ điều kiện tới người dùng sớm.

Không có kiểm thử đáng tin, WIP limit chỉ khiến lỗi tập trung ở cột Verify; phải cải tiến cả **kỹ thuật lẫn chính sách**.

### 27.4. Lean giữ mục tiêu của hệ thống

Nếu một nhóm frontend giao 20 màn hình cho nhóm backend nhưng người học chưa thể đăng ký, hệ thống chưa tạo giá trị end-to-end. Lean nhắc tối ưu **toàn dòng**, giảm chờ và làm lại, không tối ưu số việc từng bộ phận báo hoàn thành.

## 28. Khi nhiều nhóm cùng tham gia một dòng giá trị

Một luồng đăng ký có thể cần nhóm sản phẩm, nền tảng xác thực, dữ liệu hoặc đội vận hành. Không thể giải quyết mọi phụ thuộc bằng cách đặt WIP limit cho nhóm sản phẩm.

### 28.1. Mẫu bản đồ phụ thuộc

| Nhu cầu của dòng giá trị | Bên phụ thuộc | Điều cần rõ | Cách giảm chờ |
| --- | --- | --- | --- |
| Đăng ký khóa | Xác thực dùng chung | Hợp đồng API, quyền và dữ liệu test | Contract tests, sandbox tự phục vụ nếu được phép |
| Xác nhận trạng thái | Enrollment service | Semantics của Active/Cancelled/Retry | Ví dụ hành vi chung, schema/versioning phù hợp |
| Mở bài đầu | Nội dung và quyền học | Quy tắc tài khoản và quyền | Integration tests, owner quyết định |
| Release | Platform/Operations | Pipeline, gate, rollback | Đưa yêu cầu sớm, self-service trong quyền |
| Migration | DBA/Security | Dữ liệu, phê duyệt, phục hồi | Test rehearsal, tài liệu và lịch rõ |

### 28.2. Blocker ngoài nhóm vẫn là blocker thật

Nếu một PBI đã start và phải đợi môi trường bên ngoài, nó vẫn WIP trong workflow đang đo. Tổ chức có thể đo **thời gian chờ theo nguyên nhân** để cải tiến việc phối hợp; đừng “ném ticket sang nhóm khác” rồi cho biến mất khỏi dashboard.

### 28.3. Không tạo nhiều bảng không kết nối

Nếu nhóm UI, API và DB mỗi nơi có bảng riêng, một PBI xuyên giá trị có thể bị báo Done ở ba nơi mà **Increment tích hợp vẫn chưa Done**. Có thể dùng một **bảng dòng giá trị cấp sản phẩm**, với subtask hoặc liên kết bảng chuyên môn khi cần; trách nhiệm end-to-end và điểm Done phải rõ.

### 28.4. Khi nhiều Scrum Teams cùng một sản phẩm

Theo Scrum, các Scrum Teams cùng sản phẩm chia sẻ **Product Goal, Product Backlog, Product Owner và Definition of Done**; mỗi Scrum Team có Sprint Goal và Sprint Backlog riêng. Một hệ thống Kanban xuyên nhóm có thể giúp quan sát phụ thuộc, nhưng **không tự tạo một Product Owner mới cho từng tầng kỹ thuật** hoặc thay cấu trúc trách nhiệm Scrum.

### 28.5. WIP limits xuyên nhóm

Một WIP limit của workflow chung không nhất thiết là tổng đơn giản của giới hạn các nhóm. Nếu một PBI có task của hai nhóm song song, phải xác định **một work item giá trị** được tính WIP một lần ở cấp sản phẩm, không đếm task con như nhiều PBI. Có thể theo dõi thêm WIP kỹ thuật nội bộ, nhưng không cộng hai phép đo không cùng đơn vị.

## 29. Bài toán ưu tiên khi có deadline, hợp đồng và an toàn

Nhóm nhận ba yêu cầu cùng lúc:

- **A:** Sửa lỗi phân quyền đang lộ dữ liệu người học.
- **B:** Hoàn tất một báo cáo bắt buộc trước ngày nghiệm thu hợp đồng.
- **C:** Xây đề xuất email xác nhận mới do một stakeholder nêu.

### 29.1. Cách xử lý

**A:** Kích hoạt ứng cứu theo mức độ và quyền security/incident; nếu dùng expedite, công khai nó chiếm capacity, ghi ảnh hưởng những item khác. **Không đợi replenishment định kỳ**.

**B:** Xác định deadline và bằng chứng thật, xem Work Item Age, blocker, khả năng hoàn tất, thẩm quyền sửa mốc nếu có. Có thể ưu tiên như Fixed Date và cảnh báo sớm khi forecast rủi ro.

**C:** Làm rõ nhu cầu, giá trị và phạm vi. Một đề nghị bằng lời không tự là PBI phải làm ngay; nếu thay nghĩa vụ hợp đồng cần change control phù hợp.

### 29.2. Phân biệt deadline và SLE

SLE “khoảng 85% item ≤10 ngày” không phải lời hứa báo cáo B sẽ đáp ứng mốc hợp đồng. Deadline có thể có hậu quả riêng; cần dự báo và điều chỉnh trong thẩm quyền.

### 29.3. Không “expedite mọi thứ”

Khi A, B, C đều được dán nhãn đỏ, hệ thống mất khả năng ưu tiên. Một chính sách rõ về **mức độ thiệt hại, fixed date và giá trị** giúp nhóm xử lý khác nhau thay vì tranh luận theo người lên tiếng lớn nhất.

## 30. Workshop 120 phút: tạo hệ thống Kanban đầu tiên

Đây là **kịch bản thực hành theo nhóm** có thể thực hiện trực tiếp hoặc từ xa. Thời gian và số người chỉ là tham khảo.

### 30.1. Chuẩn bị

**Đầu vào:**

- Một dòng giá trị có nhu cầu người dùng rõ.
- Tối thiểu 8–12 PBI/defect/technical items minh họa hoặc dữ liệu thực được phép dùng.
- Mô tả cách công việc đang đi qua nhóm.
- Vài kết quả Cycle Time, throughput và item đang WIP (nếu có).
- Product Goal và một ví dụ DoD/chuẩn chất lượng.
- Người tham gia đại diện các kỹ năng, Product Owner/đại diện giá trị và người hiểu phụ thuộc.

**Nếu không có dữ liệu lịch sử**, dùng bộ dữ liệu giả định của bài nhưng phải ghi rõ **SLE và WIP limit ban đầu là giả thuyết**, không được coi là thông số đã được chứng minh.

### 30.2. Agenda thực hành

| Phần | Thời lượng | Hoạt động | Bằng chứng đầu ra |
| --- | ---: | --- | --- |
| 1. Mục tiêu và dịch vụ | 10 phút | Chọn người dùng, outcome, phạm vi dòng | Service statement |
| 2. Vẽ dòng công việc thật | 15 phút | Các trạng thái, hàng chờ, DoW start/finish | Value stream map |
| 3. Chọn work item và DoD | 15 phút | PBI vs task, loại việc, quality | Work item policy |
| 4. Bảng và WIP limit | 20 phút | Cột, hạn mức cột/tổng, pull | Board draft |
| 5. Blocked/expedite/replenishment | 15 phút | Quyền, ngoại lệ, mẫu thẻ | Explicit policies |
| 6. Flow metrics và SLE | 15 phút | Tính Age, CT, P85, throughput | Metric definitions |
| 7. Mô phỏng ba tình huống | 20 phút | WIP đầy, blocker, incident | Decision log |
| 8. Kế hoạch thử và review | 10 phút | Guardrails, điểm xem lại, owner | Experiment brief |
| **Tổng** | **120 phút** | | |

### 30.3. Phân vai cho mô phỏng

Có thể dùng các vai **không phải vai trò Scrum bắt buộc**:

- **Điều phối viên:** Hỏi lý do trước khi chuyển thẻ, ghi decision log.
- **Người nhìn giá trị:** Bảo đảm PBI được ưu tiên theo nhu cầu người dùng.
- **Người hỗ trợ Build:** Đề xuất cách triển khai lát cắt nhỏ.
- **Người hỗ trợ Review/CI:** Nêu điều kiện PR/test và hàng chờ.
- **Người hỗ trợ Verify:** Đối chiếu DoD và chất lượng.
- **Người quan sát flow:** Đếm WIP, Age và vi phạm policy.
- **Người đóng vai sự cố:** Đưa yêu cầu expedite và tác động.

Người tham gia có thể đổi vai để hiểu khó khăn ở nhiều vị trí. **Không dùng vai diễn để chấm năng suất cá nhân**.

### 30.4. Ba thẻ tình huống dùng ngay

**Thẻ 1 — Review đầy:** Build còn slot, Review 2/2, tổng WIP 5/5. Một Developer muốn kéo thêm feature. Hỏi nhóm sẽ làm gì, điều nào bị cấm theo policy và ai có thể hỗ trợ?

**Thẻ 2 — Item già blocked:** K-02 Age 12 ngày, SLE P85 10 ngày; API đối tác chưa xác nhận hợp đồng trạng thái. Hỏi có được chuyển Ready để không tính WIP không, ai cần escalation và điều gì có thể làm trong khi chờ?

**Thẻ 3 — Sự cố bảo mật:** Hệ thống đang để người học xem dữ liệu của người khác. Hỏi khi nào dùng expedite, ai có quyền ứng cứu, tác động tới WIP và những tiêu chuẩn không được bỏ?

### 30.5. Sản phẩm cần nộp sau workshop

Một bản ngắn khoảng **1–3 trang tương đương**, có:

- Bảng Kanban và DoW.
- Sơ đồ/định nghĩa luồng giá trị, loại item.
- WIP limits và lý do thử ban đầu.
- Chính sách blocked/expedite/pull/replenishment.
- Cách đo bốn flow metrics và SLE.
- Ít nhất ba quyết định khi mô phỏng.
- Kế hoạch thử thay đổi có guardrails.

Không chấm bài theo **số cột nhiều hay ít**. Đánh giá sự nhất quán và khả năng ra quyết định.

## 31. Bài tập A: đọc bảng và quyết định kéo việc

Nhóm có bảng:

| Ready | Build (≤3) | Review (≤2) | Verify (≤2) | Done |
| --- | --- | --- | --- | --- |
| K-06 | K-01, Age 5 | K-02, Age 9, blocked | K-03, Age 8 | K-00 |
| K-07 | K-04, Age 2 | K-05, Age 4 |  |  |
| K-08 | | | | |

Quy định **tổng WIP ≤5**, blocked tính WIP, Done tính khi đạt DoD, Ready nằm ngoài điểm START. Không có expedite đang hoạt động.

### Câu hỏi

1. Tính WIP của Build, Review, Verify và toàn dòng.
2. Nhóm có được kéo K-06 từ Ready vào Build ngay không? Tại sao?
3. Review có chỗ để chuyển K-01 từ Build không?
4. Nếu K-03 đạt DoD hôm nay, tổng WIP và throughput thay đổi thế nào?
5. Sau khi K-03 Done, K-05 đạt exit Review và được kéo vào Verify, WIP tổng có đổi không?
6. Sau khi K-05 sang Verify, Review còn chỗ; K-01 đủ điều kiện chuyển Review. Tổng WIP có đổi không?
7. Giả sử K-02 bị chặn vì chờ xác nhận API, có được chuyển về Ready và trừ khỏi WIP không?
8. K-02 đang ở Age 9 ngày, SLE tham khảo là 85% ≤10 ngày. Có nghĩa K-02 đã 90% hoàn thành không?
9. Nếu một stakeholder nói “hãy làm K-07 gấp”, cần hỏi thêm điều gì?
10. Thiết kế hành động Daily Kanban trong ba câu.

### Lời giải

**Câu 1:** Build có 2, Review 2, Verify 1, tổng \(2+2+1=5\). Ready 3 item và Done 1 item không thuộc WIP chính.

**Câu 2:** **Không** trong trạng thái hiện tại vì tổng WIP = 5/5, dù Build mới 2/3. Trước hết cần hoàn tất hoặc xử lý ngoại lệ hợp lệ.

**Câu 3:** Không, Review đã 2/2; cần item Review đi tiếp theo entry/exit policy trước.

**Câu 4:** WIP từ 5 xuống 4; throughput của kỳ chứa hôm nay tăng thêm **1 PBI Done**, nếu K-03 đạt DoD thật.

**Câu 5:** WIP tổng vẫn **4**, vì chỉ chuyển trạng thái một PBI đang mở.

**Câu 6:** WIP tổng vẫn **4**; K-01 vẫn là item đã start, chỉ đổi từ Build sang Review.

**Câu 7:** Không theo policy hiện tại. K-02 vẫn WIP và Age tăng cho tới Done/hủy theo chính sách minh bạch. Cần gỡ blocker hoặc xử lý quyết định thật, không chuyển để làm đẹp số.

**Câu 8:** Không. \(9/10=90\%\) chỉ là tỷ lệ **tuổi so với mốc tham khảo**, không phải tỷ lệ công việc hoàn thành hoặc xác suất còn lại.

**Câu 9:** Điều gì khiến K-07 khẩn? Có deadline/thỏa thuận thật, hậu quả và quyền nào? Có đáp ứng policy expedite hay chỉ nên điều chỉnh thứ tự Ready? Việc thay ưu tiên có ảnh hưởng Sprint Goal, Product Goal và nghĩa vụ không?

**Câu 10 — Hành động mẫu:** “Ưu tiên hoàn tất K-03 để giải phóng Verify và tổng WIP; kéo K-05 xuống Verify nếu điều kiện đạt. Đồng thời cùng người liên quan gỡ blocker API cho K-02, không khởi động thêm K-06. Xem lại Work Item Age và khả năng đạt DoD tại Daily tiếp theo.”

## 32. Bài tập B: tính flow metrics và viết SLE đúng

Mẫu 20 Cycle Time, đơn vị ngày làm việc:

~~~text
2, 3, 3, 4, 4, 5, 5, 5, 6, 6,
6, 7, 7, 8, 8, 9, 10, 11, 13, 18
~~~

Throughput sáu tuần:

~~~text
3, 5, 4, 2, 6, 4 PBI Done/tuần
~~~

Nhóm đang có một PBI chưa Done với Work Item Age 12 ngày. Giả sử DoW từ Build tới DoD và các PBI có cùng loại tương đối phù hợp.

### Câu hỏi

1. Xác định trung vị Cycle Time.
2. Tính P85 và P95 bằng nearest-rank.
3. Viết một SLE gồm loại item, ranh giới, tỷ lệ, thời gian và đơn vị.
4. Có bao nhiêu item trong mẫu ≤10 ngày?
5. Tính throughput trung bình mỗi tuần.
6. Nếu còn 16 PBI tương đồng, phép chia tham khảo cho số tuần là bao nhiêu?
7. Có thể hứa sẽ giao chắc chắn trong số tuần đó không?
8. Với PBI Age 12 ngày, có thể dự báo “quá SLE 2 ngày nên còn -2 ngày” không?
9. Vì sao cần xem Work Item Age ngoài Cycle Time?
10. Nếu nhóm vừa hạ DoD để có nhiều Done hơn, metric có còn đo cùng chất lượng không?

### Lời giải

**Câu 1:** Hai vị trí giữa 10 và 11 đều 6, nên median = **6 ngày**.

**Câu 2:**

\[
\text{P85 rank}=\lceil20\times0{,}85\rceil=17\Rightarrow10\ \text{ngày}
\]

\[
\text{P95 rank}=\lceil20\times0{,}95\rceil=19\Rightarrow13\ \text{ngày}
\]

**Câu 3:** “Đối với PBI standard, đo từ lúc được kéo vào Build tới khi đạt DoD theo workflow đã định, kỳ vọng khoảng **85% item hoàn tất trong không quá 10 ngày làm việc**, dựa trên dữ liệu 20 PBI gần đây.”

**Câu 4:** **17/20 item**, tức 85% trong mẫu.

**Câu 5:** \((3+5+4+2+6+4)/6=24/6=4\) PBI/tuần.

**Câu 6:** \(16/4=4\) tuần là **ước lượng tham khảo thô**.

**Câu 7:** Không. Phải xét biến động 2–6 item/tuần, độ tương đồng PBI, trạng thái WIP, blocker, capacity, chất lượng và nghĩa vụ. Cần dự báo với bất định thay vì hứa chắc.

**Câu 8:** Không. SLE phân vị không là công thức tính thời gian còn lại cho một item sống sót tới ngày 12.

**Câu 9:** Cycle Time chỉ có đầy đủ cho item đã Done, dễ bỏ quên item chưa Done đang già đi; Age là tín hiệu hiện tại để can thiệp.

**Câu 10:** Không. Đổi DoD làm thay đổi điểm Done và mức chất lượng; việc so sánh throughput trước/sau sẽ sai nếu không ghi nhận và điều chỉnh định nghĩa. **Không hạ DoD chỉ để làm số đẹp**.

## 33. Bài tập C: thiết kế chính sách blocked và expedite

Một nhóm đang có tổng WIP 5/5:

- K-01: Build, chờ test data.
- K-02: Review, blocked vì contract API.
- K-03: Verify, có test quyền học chưa đạt.
- K-04: Build, đang thực hiện bình thường.
- K-05: Review, đang chờ CI.

Ba yêu cầu tới cùng lúc:

1. **INC-01:** Dữ liệu đăng ký của tài khoản B có thể được nhìn bởi tài khoản A trên production.
2. **FIX-02:** Tính năng báo cáo bắt buộc cần đủ bằng chứng cho mốc nghiệm thu sắp tới.
3. **IDEA-03:** Một stakeholder muốn thêm dashboard cá nhân hóa cho người học.

### Câu hỏi

1. Nhóm có được bỏ K-02 ra khỏi WIP vì blocked không?
2. Đâu là ứng viên rõ ràng nhất cho đường expedite, và cần ai xử lý?
3. Nếu policy có 5 slot bình thường + 1 expedite, WIP thực sau khi kích hoạt INC-01 là bao nhiêu?
4. Có cần dừng/gián đoạn PBI nào để xử lý sự cố? Nên ghi nhận ra sao?
5. FIX-02 có bắt buộc là expedite chỉ vì có deadline không?
6. IDEA-03 có được kéo ngay vào Build vì stakeholder rất muốn không?
7. K-03 có thể chuyển Done khi test quyền học thất bại không?
8. Nêu ba hành động gỡ blocker trong quyền.
9. Sau khi xử lý INC-01, cần đánh giá điều gì?
10. Viết chính sách expedite gọn 4–6 câu phù hợp.

### Gợi ý lời giải

**Câu 1:** Không; theo DoW đã chọn, blocked vẫn WIP. Cần người giải blocker và điểm kiểm tra lại.

**Câu 2:** INC-01 là sự cố phân quyền đang ảnh hưởng dữ liệu thật, cần ứng cứu theo incident/security policy với người có quyền; không chờ cuộc họp thường kỳ.

**Câu 3:** Nếu cả 5 slot bình thường đang dùng và có một ngoại lệ thực sự được kích hoạt, tổng **6 item WIP** phải hiển thị: 5 normal + 1 expedite.

**Câu 4:** Có thể cần tạm ngưng hoặc giảm công suất cho một số PBI, nhưng không làm chúng biến mất khỏi WIP. Ghi item bị gián đoạn, người xử lý và ảnh hưởng tới forecast.

**Câu 5:** Không mặc định; loại Fixed Date cần quản lý rủi ro sớm. Chỉ expedite nếu đáp ứng điều kiện thiệt hại khẩn theo policy có thẩm quyền.

**Câu 6:** Không; nó cần được làm rõ giá trị, phạm vi và quyền, rồi bổ sung Ready theo ưu tiên/capacity thích hợp. Nếu thay nghĩa vụ hợp đồng, cần change control.

**Câu 7:** Không. Nếu DoD yêu cầu quyền học đúng, test thất bại nghĩa PBI chưa Done.

**Câu 8:** Pair với nhóm API để làm rõ semantics, tạo contract test với dữ liệu giả, liên hệ người quản lý môi trường để cấp test data theo quyền; đồng thời hỗ trợ review item gần Done.

**Câu 9:** Phân tích nguyên nhân không đổ lỗi, chất lượng cơ chế phát hiện, thay đổi policy/test cần thiết, thời gian gián đoạn, WIP, tác động tới người học và deadline.

**Câu 10 — Chính sách mẫu:** “Đường expedite chỉ kích hoạt bởi incident/rủi ro được phân loại khẩn theo người có quyền. Tối đa một expedite; nó vẫn tính WIP thực và có thể dùng một slot ngoại lệ đã công khai. Khi kích hoạt, người điều phối ghi những item bị gián đoạn và thông báo rủi ro mốc. Công việc ứng cứu phải giữ an toàn, quyền dữ liệu và quy trình khôi phục. Sau khi kết thúc, nhóm xem nguyên nhân, chất lượng và tác động tới dòng bình thường.”

## 34. Bài tập D: chẩn đoán nghẽn Review và thiết kế thí nghiệm

Một nhóm có workflow Build → Review & CI → Verify → Done. Sau bốn tuần, họ ghi nhận:

| Dữ liệu minh họa | Tuần 1 | Tuần 2 | Tuần 3 | Tuần 4 |
| --- | ---: | ---: | ---: | ---: |
| WIP Review trung bình | 2 | 3 | 4 | 4 |
| Số PBI đạt Done | 4 | 3 | 2 | 2 |
| Age cao nhất của item Review tại cuối tuần | 5 | 8 | 11 | 15 |
| Lỗi tích hợp phát hiện muộn | 1 | 2 | 3 | 4 |

Trước đó nhóm **chưa có WIP limit Review rõ**, PR thường rất lớn và chỉ một reviewer chính có quyền merge.

### Câu hỏi

1. Những dấu hiệu nào gợi ý Review & CI có thể là nút nghẽn?
2. Có thể kết luận reviewer “lười” hoặc “không giỏi” không?
3. Đề xuất một WIP limit Review ban đầu và cách kiểm tra nó.
4. Nếu nhóm đặt Review ≤2 nhưng Build cứ đẩy thêm vào “Waiting Review” vô hạn, có cải tiến thật không?
5. Kể hai cải tiến kỹ thuật và hai cải tiến chính sách có thể thử.
6. Nêu guardrails để không tăng tốc review bằng cách bỏ test bắt buộc.
7. Dữ liệu bốn tuần có đủ chứng minh nhân quả không?
8. Thiết kế PDSA qua hai tuần để kiểm tra giả thuyết.
9. Khi thấy WIP Review giảm mà throughput vẫn thấp, nhóm nên hỏi gì?
10. Nếu yêu cầu review bởi người có quyền là bắt buộc, nhóm nên xử lý ra sao?

### Gợi ý lời giải

**Câu 1:** Review WIP từ 2 lên 4, Age cao nhất từ 5 lên 15 ngày, throughput giảm 4 xuống 2 và lỗi muộn tăng. Đây là tín hiệu cần phân tích, chưa đủ khẳng định nguyên nhân duy nhất.

**Câu 2:** Không. PR lớn, quyền một người, CI flaky, ưu tiên khác và năng lực hỗ trợ có thể cùng góp phần. Cần hỏi và xem dữ liệu hệ thống.

**Câu 3:** Thử Review ≤2, đồng thời xem **tổng WIP**, blocked time, Cycle Time và khả năng hoàn tất. Nếu giới hạn làm việc bị chờ quá lâu trong Build, cần hỗ trợ nút nghẽn hoặc điều chỉnh policy có căn cứ.

**Câu 4:** Không. Hàng chờ chỉ đổi tên. Cần nhìn WIP từ START tới Done, kể cả những item waiting.

**Câu 5:** Kỹ thuật: PR nhỏ/CI ổn định/contract tests; chính sách: reviewer dự phòng phù hợp quyền, ưu tiên review item già trước pull mới, WIP giới hạn rõ và hỗ trợ pairing.

**Câu 6:** DoD và test bảo mật/tích hợp phải giữ; theo dõi defect sau release, rollback, flaky tests và nguy cơ dữ liệu.

**Câu 7:** Không. Cần kiểm tra loại PBI, năng lực, lịch nghỉ, mức khó và các yếu tố thay đổi. Dữ liệu là bằng chứng về hiện tượng, chưa tự xác lập quan hệ nhân quả.

**Câu 8:** **Plan:** “Giảm PR lớn và giới hạn Review ≤2 sẽ giảm queue age mà không giảm quality.” **Do:** Thử hai tuần, nhờ người có quyền hỗ trợ review và theo dõi Age. **Study:** So throughput, Cycle Time, WIP, lỗi và guardrail với baseline. **Act:** Giữ/điều chỉnh giới hạn hoặc xử lý nguyên nhân khác.

**Câu 9:** Có thể thiếu PBI Ready, test Verify bị nghẽn, DoD còn nhiều lỗi, công việc tương lai khó hơn hoặc Age của item dở tăng. Không kết luận chỉ từ WIP Review.

**Câu 10:** Không bỏ review trái quyền. Chuẩn bị PR nhỏ, reviewer đủ năng lực và có quyền, lịch dự phòng hoặc cải thiện công cụ/đầu vào để review hiệu quả hơn.

## 35. Mẫu nộp bài: Kanban System Design Brief

Đây là **mẫu học tập** nhằm kiểm tra thiết kế đã đủ vận hành. Nó không phải một artifact bắt buộc của Kanban hay Scrum.

~~~text
KANBAN SYSTEM DESIGN BRIEF

1. Dịch vụ / Dòng giá trị:
   - Người dùng:
   - Outcome:
   - Loại yêu cầu phục vụ:

2. Definition of Workflow:
   - Đơn vị work item:
   - Điểm START:
   - Điểm FINISH:
   - Các trạng thái:
   - Blocked được thể hiện:
   - Cách đếm huỷ/tạm dừng:

3. Definition of Done / chuẩn chất lượng:
   - ...

4. Bảng và giới hạn:
   - Build: ...
   - Review: ...
   - Verify: ...
   - Tổng WIP: ...
   - Slot expedite nếu có:
   - Lý do chọn mức ban đầu:

5. Explicit policies:
   - Ready:
   - Entry/exit từng trạng thái:
   - Pull:
   - Khi cột downstream đầy:
   - Blocked:
   - Expedite:
   - Replenishment:
   - Class of service / fixed date:

6. Metrics:
   - WIP và thời điểm snapshot:
   - Work Item Age / đơn vị:
   - Cycle Time start -> finish:
   - Throughput / kỳ:
   - SLE và cách thiết lập:
   - Các phép đo bổ sung:

7. Feedback loops:
   - Quan sát flow:
   - Quyết định replenishment:
   - Service delivery review:
   - Cải tiến/retrospective:

8. Phụ thuộc, quyền và an toàn:
   - API/đối tác:
   - Release/hợp đồng:
   - Security/privacy:

9. Dữ liệu mô phỏng:
   - Số WIP hiện tại:
   - Item già nhất:
   - Blocker:
   - Quyết định khi total WIP đầy:
   - Quyết định khi có expedite:

10. Kế hoạch thử:
    - Vấn đề hiện tại:
    - Giả thuyết cải tiến:
    - Điều thay đổi:
    - Chỉ số mục tiêu:
    - Guardrails:
    - Điểm xem lại:
    - Người phối hợp:
~~~

### 35.1. Cách dùng mẫu

Tập trung vào **những điều người khác có thể kiểm chứng**. Nếu viết “mọi người chủ động hỗ trợ nhau”, nên bổ sung “khi Review đầy thì không kéo item mới, người có năng lực được hỗ trợ review theo quyền”. Nếu viết “SLE là 10 ngày”, phải có **tỷ lệ, loại item, ranh giới và đơn vị**.

### 35.2. Không bắt nhóm tái thiết kế một hệ thống hoàn toàn mới ngay

Kanban có tinh thần **bắt đầu từ cách làm hiện tại và cải tiến theo bước nhỏ**. Brief là công cụ thảo luận, không được dùng để ép toàn nhóm thay công cụ, đổi nhân sự hoặc bỏ quy trình cần thiết trong một ngày.

## 36. Thử nghiệm cải tiến có kiểm soát: giảm WIP và xem lại sau hai tuần

Một đội phát hiện Review thường có từ 3–5 PBI, tổng WIP khoảng 8–10, nhiều item Age cao và lỗi phát hiện muộn. Họ muốn thử **Review ≤2 và tổng WIP ≤5** trong hai tuần phù hợp.

### 36.1. Plan — phát biểu giả thuyết kiểm chứng được

> “Nếu giảm số PBI mở và ưu tiên hoàn tất review/Verify trước khi bắt đầu thêm, thời gian chờ Review và Cycle Time của các PBI tương đồng có thể giảm, trong khi throughput và chất lượng không xấu đi.”

**Đường cơ sở:** Ghi ranh giới DoW, WIP theo ngày, số PBI Done từng tuần, Cycle Time, Work Item Age và lỗi. Ghi cả item chưa Done để tránh survivor bias.

### 36.2. Do — thực hiện thay đổi nhỏ

1. Công khai policy WIP Review và tổng.
2. Giữ blocked trong WIP; không chuyển về Ready để né giới hạn.
3. Trước khi kéo PBI mới, xem liệu có thể hỗ trợ item đang gần Done.
4. Chia PR lớn, bổ sung test cần thiết và trao đổi API sớm.
5. Ghi các ngoại lệ expedite, sự cố và nguyên nhân vi phạm policy.
6. Nếu một kiểm soát an toàn bắt buộc gây chờ, chuẩn bị bằng chứng và phối hợp người có quyền.

### 36.3. Study — ví dụ dữ liệu sau thử

Giả sử có hai mẫu mỗi mẫu 12 item Done, theo cùng định nghĩa Cycle Time:

~~~text
Trước thử (ngày làm việc):
3, 4, 4, 5, 5, 6, 7, 8, 9, 11, 13, 15

Sau thử (ngày làm việc):
2, 3, 3, 4, 4, 5, 5, 6, 7, 8, 9, 11
~~~

Tính gần đúng:

| Chỉ số | Trước | Sau | Diễn giải |
| --- | ---: | ---: | --- |
| Số item Done trong mẫu | 12 | 12 | **Không chứng minh throughput tăng** nếu hai kỳ khác độ dài |
| Cycle Time trung vị | \((6+7)/2=6,5\) ngày | \((5+5)/2=5\) ngày | Xu hướng cần kiểm tra cùng loại việc |
| P85 nearest-rank | Vị trí 11 → **13 ngày** | Vị trí 11 → **9 ngày** | Mẫu nhỏ, phân vị nhạy với vài item |
| Cycle Time lớn nhất | 15 ngày | 11 ngày | Không chứng minh mọi rủi ro đã mất |

P85 nearest-rank của 12 item:

\[
\lceil0{,}85\times12\rceil=\lceil10{,}2\rceil=11
\]

### 36.4. Guardrails không thể thiếu

- Test theo DoD vẫn đạt, không bớt yêu cầu phân quyền.
- Số lỗi nghiêm trọng sau release không tăng.
- CI ổn định và kết quả test không bị làm xanh bằng rerun tùy tiện.
- Không có nhóm item khó bị giữ mãi ở WIP trong khi chỉ Done item dễ.
- Không tăng làm thêm quá sức để giữ số WIP thấp.
- Dòng giá trị người học thực sự được cải thiện, không chỉ báo cáo task.

### 36.5. Act — quyết định theo bằng chứng

Nếu Age của item dở giảm, Cycle Time tốt hơn, chất lượng giữ, nhóm có thể tiếp tục policy. Nếu Review WIP giảm nhưng Verify dày lên, **nút nghẽn có thể chỉ di chuyển**; cần điều chỉnh năng lực/tự động hóa và chính sách phù hợp.

Không nên tuyên bố “WIP limit gây giảm P85 4 ngày” như quan hệ nhân quả chắc chắn chỉ từ hai mẫu nhỏ. Loại PBI, đội hình, tình trạng môi trường và năng lực test có thể khác.

### 36.6. Chu kỳ cải tiến không kết thúc sau hai tuần

Kanban là cách quản lý và phát triển năng lực cung cấp dịch vụ. Khi Product Goal, workflow hoặc quy định thay đổi, cần xem lại DoW, policy, class of service, WIP và SLE theo dữ liệu.

## 37. Những sai lầm thường gặp khi thiết kế hệ thống Kanban

**1. “Có ba cột To do – Doing – Done là đã vận hành Kanban.”** Cần hiểu loại item, DoW, policy, WIP và cách cải tiến flow.

**2. “Càng nhiều cột càng chuyên nghiệp.”** Chỉ tách khi trạng thái có nghĩa và giúp quyết định.

**3. “Ready luôn tính WIP.”** Tùy điểm START của DoW; bài này Ready nằm ngoài WIP chính.

**4. “Blocked có thể đưa ra khỏi WIP để tạo chỗ.”** Theo policy bài này, blocked vẫn WIP và Age tăng.

**5. “Một subtask UI và một PBI mẹ đều tính throughput.”** Đếm sai đơn vị, làm số lượng Done giả.

**6. “WIP limit theo từng cột đủ rồi, không cần xem tổng.”** Cần hiểu cách phối hợp các giới hạn nếu đặt cả hai.

**7. “Build còn một ô trống thì phải kéo thêm.”** Nếu tổng đầy hoặc downstream nghẽn, kéo thêm có thể gây hại.

**8. “WIP limit phải luôn đầy.”** Đó là giới hạn tối đa, không phải mục tiêu số lượng thẻ.

**9. “Giảm WIP càng thấp càng tốt.”** Quá thấp có thể làm mất song song hữu ích và giảm throughput.

**10. “Giới hạn WIP cứ tính bằng số người ×2.”** Không có công thức phổ quát; xem kỹ năng, nút nghẽn và dữ liệu.

**11. “Một item blocked là người phụ trách làm việc kém.”** Nguyên nhân có thể là phụ thuộc tổ chức, công cụ, quyền hoặc điều kiện kỹ thuật.

**12. “Tạo cột Pending Review không giới hạn giúp giải phóng Build.”** Nó có thể chỉ che hàng chờ thật.

**13. “Expedite không phải WIP.”** Công việc đã bắt đầu vẫn phải được hiển thị và tính, kể cả ngoại lệ.

**14. “Mọi người nói gấp thì mọi item đều expedite.”** Thiếu chính sách mức độ thiệt hại, ưu tiên mất ý nghĩa.

**15. “Fixed Date nghĩa đến sát deadline mới bắt đầu tăng tốc.”** Cần xem rủi ro, phụ thuộc và khả năng hoàn tất sớm.

**16. “Technical improvement không tạo giá trị nên không cần capacity.”** Một số cải tiến CI, test, security giúp dòng bền vững; cần ưu tiên có căn cứ.

**17. “Daily Kanban là cuộc báo cáo mỗi người làm gì hôm qua.”** Nên nhìn item già, blocker, WIP và việc có thể Done.

**18. “Họp nhiều hơn là cải tiến flow.”** Vòng phản hồi cần quyết định và hành động, không chỉ cập nhật.

**19. “Cycle Time tính từ ngày tạo ticket.”** Phải theo START đã định; ngày tạo có thể nằm trước nhiều tuần.

**20. “Item đã code xong là Done.”** Nếu DoD đòi tích hợp/test, code xong chưa đủ.

**21. “Sprint Review là cổng xác định Done.”** Scrum không coi Review là release gate; Increment Done theo DoD.

**22. “Work Item Age bằng phần trăm hoàn thành.”** Tuổi là thời gian trôi qua.

**23. “SLE P85 10 ngày nghĩa mọi item xong trước ngày 10.”** SLE là kỳ vọng theo phân bố, không bảo đảm từng item.

**24. “Age 12 và SLE 10 nghĩa còn -2 ngày.”** Không suy residual time bằng phép trừ phân vị.

**25. “Cycle Time của các item đã Done là đủ.”** Cần xem item chưa Done, bị chặn và tuổi cao.

**26. “Throughput là số PR merge.”** Chỉ đúng nếu work item/DoW đã định nghĩa như vậy; PBI Done theo DoD có nghĩa khác.

**27. “Cứ chia ticket nhỏ tùy ý để tăng throughput.”** Cần lát cắt giá trị và giữ chất lượng.

**28. “Little's Law cho biết deadline P95.”** Nó là quan hệ trung bình dưới điều kiện phù hợp.

**29. “CFD tự cho biết reviewer có lỗi.”** Biểu đồ chỉ nêu hiện tượng, cần điều tra nguyên nhân.

**30. “Flow Efficiency càng cao bằng cách bỏ test càng tốt.”** Quality guardrails không được hy sinh.

**31. “Giảm WIP xong thì có thể tự hứa ngày giao.”** Cần dữ liệu và bất định dự báo; phụ thuộc có thể thay đổi.

**32. “Một SLE hợp mọi loại incident, PBI, migration.”** Cần phân loại khi đặc điểm dịch vụ khác đáng kể.

**33. “Không cần chính sách hủy, cứ kéo item về Ready.”** Việc hủy/tạm dừng cần lý do, dấu vết và cách đo minh bạch.

**34. “Càng nhiều màu thẻ càng dễ quản lý.”** Màu chỉ hữu ích khi có ý nghĩa nhất quán và người dùng đọc được.

**35. “Làm Kanban phải bỏ Scrum.”** Kanban có thể bổ sung quản lý flow trong Scrum.

**36. “Các Scrum Teams cùng sản phẩm có thể mỗi nhóm dùng DoD riêng.”** Scrum yêu cầu DoD chung cho cùng sản phẩm.

**37. “Một nhóm nền tảng chậm thì nhóm sản phẩm không cần đo blocked time.”** Phụ thuộc ngoài nhóm vẫn ảnh hưởng dòng giá trị.

**38. “Bảng đẹp chứng minh người học nhận giá trị.”** Cần xem outcome sử dụng, chất lượng và phần sản phẩm có thể dùng.

**39. “Thử WIP limit mới mà không có guardrails.”** Số liệu flow tốt hơn có thể che lỗi hoặc quá tải nhân sự.

**40. “Nếu số liệu sau hai tuần đẹp hơn thì chắc do chính sách WIP.”** Mẫu nhỏ không tự chứng minh nhân quả.

**41. “Một sự cố dữ liệu có thể chờ Daily Kanban rồi mới xử lý.”** Incident phải xử lý theo quyền và mức độ ngay.

**42. “Bảo mật/luật là rào cản cần xóa để flow nhanh.”** Kiểm soát bắt buộc phải giữ; cải tiến cách chuẩn bị bằng chứng và hợp tác.

**43. “Chỉ cần WIP limit chặt là khỏi cần CI/TDD.”** Phải cải tiến kỹ thuật để giảm lỗi và chờ.

**44. “Tổ chức phải tái cấu trúc mọi nhóm trước khi dùng Kanban.”** Có thể bắt đầu từ hệ thống hiện tại và cải tiến theo bằng chứng.

**45. “Số lượng item đang mở cho biết năng suất từng người.”** WIP là thông tin trạng thái hệ thống, không là thước đo công trạng cá nhân.

## 38. Rubric đánh giá bản thiết kế Kanban theo năng lực áp dụng

Thay vì chấm số cột, số màu hay số thẻ, hãy đánh giá người học có **thiết kế một hệ thống ra quyết định nhất quán** hay không.

### 38.1. Bảng tiêu chí 100 điểm

| Năng lực | Điểm tối đa | Bằng chứng đạt |
| --- | ---: | --- |
| **Hiểu dịch vụ và dòng giá trị** | 10 | Người dùng, outcome, phạm vi và rủi ro rõ |
| **Definition of Workflow** | 15 | Loại item, START/FINISH, trạng thái, DoD rõ |
| **Board và WIP limits** | 20 | Giới hạn cột/tổng nhất quán, phản ứng khi đầy |
| **Explicit policies** | 15 | Ready, pull, blocked, expedite, class of service, entry/exit |
| **Flow metrics và SLE** | 15 | Đúng WIP, Age, CT, throughput, P85/SLE và đơn vị |
| **Quyết định khi mô phỏng** | 10 | Gỡ blocker, hỗ trợ downstream, không che WIP |
| **Tích hợp chất lượng và giá trị** | 10 | DoD, CI/test, quyền dữ liệu, phản hồi người học |
| **Thử nghiệm cải tiến** | 5 | Giả thuyết, dữ liệu, guardrail và điểm xem lại |
| **Tổng** | **100** | |

Điểm số là **khung tự đánh giá trong bài học**, không phải tiêu chuẩn chứng nhận Kanban.

### 38.2. Ba mức chất lượng bài nộp

**Cần hoàn thiện:**

- Có sơ đồ cột nhưng không rõ START/Done.
- WIP limit không có tác dụng hoặc bị né bằng cột ẩn.
- Blocked không được tính, expedite không có quyền.
- Không thể tính đúng Age/Cycle Time.
- Chỉ nói “làm nhanh hơn” mà không có bằng chứng, DoD hoặc rủi ro.

**Đạt yêu cầu:**

- Ranh giới, đơn vị công việc và DoD rõ.
- Board phản ánh trạng thái thật và giới hạn cột/tổng nhất quán.
- Chính sách kéo/blocked/expedite có thể thực hiện được.
- Đo đúng bốn flow metrics và có SLE có nguồn/giả định.
- Xử lý được các tình huống WIP đầy mà không tự gọi item chưa Done là Done.

**Tốt:**

- Thiết kế gắn với Product Goal và feedback người học.
- Có bằng chứng về nút nghẽn, năng lực và quyền thực tế.
- Có giả thuyết điều chỉnh WIP có thể bác bỏ bằng dữ liệu.
- Có guardrails chất lượng, dữ liệu và sức bền làm việc.
- Xem được phối hợp Scrum, XP, Kanban mà không chồng nghi lễ.
- Biết khi nào **giữ, đổi hoặc dừng** một chính sách.

### 38.3. Ba lỗi mang tính chặn đánh giá

Dù thiết kế trình bày đẹp, cần yêu cầu sửa nếu:

1. **Có lệnh chuyển chưa đạt DoD thành Done** để tăng throughput hoặc đạt chỉ tiêu.
2. **Có cách bỏ qua an toàn dữ liệu/quyền bắt buộc** để xử lý expedite nhanh.
3. **Có thao tác giấu WIP/blocked** làm các chỉ số không còn phản ánh đúng dòng công việc.

Những điểm này không chỉ sai kỹ thuật Kanban mà còn phá mục tiêu giao phần mềm đáng tin của Agile.

## 39. Checklist bàn giao một hệ thống Kanban có thể thử trong thực tế

### A. Giá trị và phạm vi dịch vụ

1. **Dịch vụ:** Nhóm biết đang phục vụ loại nhu cầu nào không?
2. **Người dùng:** Có biết ai nhận giá trị sau khi item Done?
3. **Outcome:** Có mục tiêu ngoài số ticket được hoàn tất?
4. **Ranh giới:** Điểm bắt đầu/kết thúc có xác định và sử dụng nhất quán?
5. **Sản phẩm:** Nếu dùng Scrum, Product Goal và Product Backlog có được tôn trọng?
6. **Loại công việc:** PBI, incident, defect và subtask có được phân biệt?
7. **Độ lớn item:** Có cách chia lát cắt đủ nhỏ mà vẫn có giá trị?

### B. Board và Definition of Workflow

8. **Trạng thái:** Mỗi cột có ý nghĩa quan sát được?
9. **Ready:** Điều kiện vào Ready có thực tế và không quá thủ tục?
10. **Build:** Developers biết khi nào kéo và khi nào chuyển review?
11. **Review:** Có kiểm tra mã, CI và quyền phù hợp?
12. **Verify:** Có test tích hợp, dữ liệu và nghiệm thu kỹ thuật theo rủi ro?
13. **Done:** DoD là chuẩn chất lượng thật, không phải lịch họp?
14. **Release:** Có phân biệt Done với phát hành và nghiệm thu hợp đồng?
15. **Blocked:** Item vẫn hiển thị, tính WIP và có người gỡ?
16. **Hủy/tạm dừng:** Có policy riêng không tạo throughput giả?
17. **Chuyển ngược:** Item quay lại Build/Review được ghi rõ và vẫn tính WIP?

### C. Giới hạn và kéo công việc

18. **WIP cột:** Giới hạn từng bước có lý do dựa trên năng lực/hàng chờ?
19. **WIP tổng:** Nếu có giới hạn tổng, có được kiểm tra cùng giới hạn cột?
20. **Không lấp đầy bằng mọi giá:** WIP limit được hiểu là mức tối đa?
21. **Pull:** Có cơ chế kiểm tra downstream trước khởi động mới?
22. **Khi đầy:** Nhóm biết phải giúp hoàn tất/gỡ blocker chứ không tạo cột ẩn?
23. **Chính sách ngoại lệ:** Có quyền và số slot expedite rõ?
24. **Expedite là WIP:** Không dùng nhãn khẩn để làm việc biến mất?
25. **Fixed Date:** Có cách xem rủi ro mốc thay vì đợi sát hạn?
26. **Improvement:** Có dành năng lực hợp lý cho kiểm thử, CI và giảm nợ kỹ thuật?
27. **Replenishment:** Có nguyên tắc chọn PBI tiếp theo từ Ready?

### D. Đo lường và kỳ vọng dịch vụ

28. **WIP:** Có đếm đúng item đã start nhưng chưa Done tại một thời điểm?
29. **Age:** Có quan sát item chưa Done, nhất là item blocked?
30. **Cycle Time:** Chỉ tính từ START tới FINISH cho item đã Done?
31. **Throughput:** Đếm đúng đơn vị Done theo kỳ?
32. **Đơn vị:** Ngày lịch hay ngày làm việc được nêu rõ?
33. **SLE:** Có tỷ lệ, thời gian, ranh giới, loại item và giả định?
34. **Phân vị:** P85/P95 được tính theo phương pháp đã công bố?
35. **Dữ liệu chưa đủ:** Không tuyên bố xác suất chính xác từ mẫu quá ít?
36. **Item dở:** Không bỏ Work Item Age vì chỉ nhìn Cycle Time đã Done?
37. **Dự báo:** Không biến throughput trung bình thành cam kết chắc chắn?
38. **Không gaming:** Không đổi nhãn, tách task giả hoặc hạ DoD để đẹp số?
39. **CFD/aging chart:** Có dùng để đặt câu hỏi, không đổ lỗi?

### E. Chất lượng, an toàn và phản hồi người dùng

40. **Definition of Done:** Có tuân chuẩn sản phẩm và tổ chức?
41. **CI/XP:** Có tích hợp và kiểm thử sớm, phù hợp rủi ro?
42. **Permission/data:** Có bảo vệ dữ liệu người học theo quyền?
43. **Concurrency/retry:** Có xem các tình huống dễ gây sai dữ liệu?
44. **Release gate:** Có giữ đúng các điều kiện bắt buộc?
45. **Outcome:** Có đo người học đăng ký và mở bài được không?
46. **Phản hồi:** Có cơ chế nghiên cứu/Review giúp Product Backlog thích ứng?
47. **Khách hàng/hợp đồng:** Có phân biệt backlog với quyền thay nghĩa vụ?

### F. Phối hợp và cải tiến liên tục

48. **Daily flow:** Có nhìn item già, blocker, khả năng Done?
49. **Không họp trùng:** Nếu dùng Scrum, Daily Scrum có thể hỗ trợ Kanban mà không tăng nghi thức vô ích?
50. **Dependency:** Có người gỡ blocker ngoài nhóm và mốc kiểm tra lại?
51. **Service delivery review:** Có đánh giá độ ổn định, chất lượng và SLE?
52. **Giả thuyết cải tiến:** Có một vấn đề cụ thể và dự đoán có thể kiểm chứng?
53. **Guardrails:** Có lỗi production, dữ liệu, DoD và nhịp bền vững?
54. **Điểm xem lại:** Có ngày/điều kiện đánh giá thay WIP limit?
55. **Nhân quả:** Có tránh tuyên bố “chính sách này chắc chắn gây cải thiện” từ mẫu nhỏ?
56. **Học hỏi:** Khi dữ liệu trái giả thuyết, nhóm có sẵn sàng đổi policy?

**Checklist là công cụ kiểm tra, không phải một quy trình phê duyệt bổ sung phải ký từng mục trước khi kéo một PBI.** Chọn mức chi tiết vừa đủ với rủi ro và khả năng vận hành.

## 40. Tổng kết: từ bảng Kanban tới hệ thống cung cấp giá trị có thể cải tiến

Thực hành thiết kế hệ thống Kanban với chính sách và giới hạn WIP là bài tập kết hợp **tư duy sản phẩm, luồng công việc, chất lượng kỹ thuật, đo lường và cộng tác**. Mục đích không phải làm mọi người luôn bận, mà là giúp **những yêu cầu quan trọng đi tới kết quả có thể sử dụng một cách đáng tin, nhìn thấy thời gian chờ và giảm tồn đọng**.

| Chỉ dựng bảng | Thiết kế và vận hành hệ thống Kanban |
| --- | --- |
| Thêm cột khi gặp vấn đề | Xác định DoW và chính sách trạng thái theo dòng công việc thật |
| Không rõ đơn vị ticket | Phân biệt PBI, subtask, defect, incident và loại dịch vụ |
| Cứ có việc là bắt đầu | Kéo việc theo năng lực, ưu tiên giá trị và giới hạn WIP |
| Blocked được bỏ ra khỏi Doing | Blocked vẫn hiện, tính WIP/Age và có người gỡ |
| Mọi yêu cầu đều khẩn | Có class of service, expedite theo quyền và chi phí gián đoạn |
| Báo “đã code” là Done | Chỉ gọi Done khi đạt DoD và có Increment sử dụng được |
| Chỉ nhìn bao nhiêu task xong | Đo WIP, Age, Cycle Time, throughput, chất lượng và outcome |
| SLE là hạn chót bắt buộc | SLE là kỳ vọng thời gian theo phân bố, có nguồn và giới hạn |
| Cột Review đầy thì cứ đẩy thêm | Giảm pull mới, hỗ trợ downstream, xử lý nguyên nhân |
| Đếm WIP một lần rồi quên | Theo dõi trạng thái và điều chỉnh policy bằng phản hồi |
| Kanban phải thay Scrum | Kanban có thể bổ sung flow trong Scrum cùng XP/CI |
| Cải tiến là đổi số WIP cho đẹp | Thử có giả thuyết, đo trước/sau, giữ guardrails và xem lại |

### 40.1. Chu trình vận hành cần nhớ

~~~mermaid
flowchart TD
    A["Hiểu người dùng, dịch vụ và giá trị"] --> B["Định nghĩa Workflow: item, START/FINISH, DoD"]
    B --> C["Trực quan hóa bảng, đặt WIP và explicit policies"]
    C --> D["Pull công việc theo năng lực và ưu tiên"]
    D --> E["Ưu tiên hoàn tất; xử lý blocked/expedite đúng quyền"]
    E --> F["Đo WIP, Age, Cycle Time, throughput, SLE và chất lượng"]
    F --> G["Thu phản hồi người dùng và nhóm"]
    G --> H["Thử cải tiến nhỏ với guardrails"]
    H --> C
~~~

### 40.2. Ba thông điệp quan trọng nhất

**Thứ nhất — Hệ thống phải có ranh giới và chính sách tường minh.** Nếu không biết khi nào một item bắt đầu, Done hoặc bị chặn, các chỉ số sẽ không đáng tin và nhóm không biết khi nào được kéo thêm việc.

**Thứ hai — WIP limit tồn tại để thay đổi hành vi, không chỉ để trang trí.** Khi Review đầy và tổng WIP chạm giới hạn, nhóm nên xem khả năng hoàn tất, gỡ blocker và hỗ trợ downstream thay vì mở thêm việc để ai cũng trông bận.

**Thứ ba — Số liệu phải phục vụ giá trị và chất lượng.** Cycle Time và throughput không thay Product Goal, DoD, quyền dữ liệu hay phản hồi thực của người học. Khi phải chọn giữa một biểu đồ đẹp và Increment đáng tin, **phải giữ chất lượng và minh bạch rủi ro**.

Trong **AGILE_DEVELOPMENT**, bài thực hành này nối **user story và Product Backlog** với nhu cầu người dùng; nối **Scrum** với mục tiêu, tính minh bạch và Increment Done; nối **XP/CI** với kiểm chứng kỹ thuật liên tục; và dùng **Kanban** để quan sát WIP, Work Item Age, Cycle Time, throughput và chính sách kéo. Với tư duy **Lean và cải tiến liên tục**, nhóm bắt đầu từ workflow thật, thử giới hạn có lý do, giữ an toàn, đo tác động và điều chỉnh theo bằng chứng.

**Kết luận:** Một hệ thống Kanban tốt không phải hệ thống có nhiều thẻ được di chuyển nhất, mà là hệ thống giúp đội **hoàn tất những lát cắt giá trị một cách ổn định, nhìn thấy và xử lý trở ngại sớm, tôn trọng giới hạn năng lực và không ngừng học cách phục vụ người dùng tốt hơn**.
